from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
from functools import partial
from typing import Any

from . import __version__
from .config import MCPServerSettings
from .models import ActionLevel, ToolResult
from .registry import ToolRegistry

logger = logging.getLogger("akki.mcp")


class MCPError(RuntimeError):
    pass


class StdioMCPClient:
    def __init__(
        self,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 15.0,
        name: str = "mcp",
    ) -> None:
        self.command = command
        self.env = env or {}
        self.timeout_seconds = timeout_seconds
        self.name = name
        self.tools: list[dict[str, Any]] = []
        self._process: subprocess.Popen[str] | None = None
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._stderr: threading.Thread | None = None
        self._lock = threading.Lock()
        self._next_id = 0

    def start(self) -> "StdioMCPClient":
        if self._process is not None:
            return self
        environment = os.environ.copy()
        environment.update(self.env)
        try:
            process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=environment,
            )
        except OSError as exc:
            raise MCPError(f"could not start {self.name}: {exc}") from exc
        self._process = process
        self._queue = queue.Queue()
        self._reader = threading.Thread(
            target=self._read_stdout,
            name=f"akki-mcp-{self.name}",
            daemon=True,
        )
        self._reader.start()
        self._stderr = threading.Thread(
            target=self._drain_stderr,
            name=f"akki-mcp-{self.name}-stderr",
            daemon=True,
        )
        self._stderr.start()
        return self

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            self._queue.put(None)
            return
        try:
            for line in process.stdout:
                self._queue.put(line)
        except (OSError, ValueError):
            pass
        finally:
            self._queue.put(None)

    def _drain_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        try:
            for line in process.stderr:
                text = line.rstrip()
                if text:
                    logger.warning("mcp[%s] %s", self.name, text)
        except (OSError, ValueError):
            pass

    def _send(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise MCPError(f"{self.name} is not running")
        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPError(f"{self.name} is not accepting input: {exc}") from exc

    def _read_message(self) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPError(f"{self.name} timed out")
            try:
                line = self._queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise MCPError(f"{self.name} timed out") from exc
            if line is None:
                raise MCPError(f"{self.name} closed its output")
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("mcp[%s] ignored non-JSON output", self.name)
                continue
            if isinstance(message, dict):
                return message

    def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            payload: dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
            }
            if params is not None:
                payload["params"] = params
            self._send(payload)
            while True:
                message = self._read_message()
                if "method" in message and "id" in message:
                    self._send(
                        {
                            "jsonrpc": "2.0",
                            "id": message["id"],
                            "error": {
                                "code": -32601,
                                "message": "method not supported by AKKI",
                            },
                        }
                    )
                    continue
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    error = message["error"]
                    if isinstance(error, dict):
                        raise MCPError(str(error.get("message") or error))
                    raise MCPError(str(error))
                return message.get("result")

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)

    def initialize(self) -> dict[str, Any]:
        result = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "akki", "version": __version__},
            },
        )
        self._notify("notifications/initialized")
        return result if isinstance(result, dict) else {}

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list")
        tools = result.get("tools") if isinstance(result, dict) else None
        self.tools = [tool for tool in tools or [] if isinstance(tool, dict)]
        return self.tools

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return self._request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def __enter__(self) -> "StdioMCPClient":
        return self.start()

    def __exit__(self, *args: object) -> None:
        self.close()


def _registered_name(server: str, tool: str) -> str:
    raw = f"mcp_{server}_{tool}"
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_")
    return cleaned[:64] or "mcp_tool"


def _parameters(schema: Any) -> dict[str, str]:
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    parameters: dict[str, str] = {}
    for key, value in properties.items():
        description = ""
        if isinstance(value, dict):
            description = str(value.get("description") or "")
        parameters[str(key)] = description
    return parameters


def _to_tool_result(payload: Any) -> ToolResult:
    if not isinstance(payload, dict):
        return ToolResult.success(str(payload), data={"mcp": payload})
    content = payload.get("content")
    parts: list[str] = []
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                parts.append(str(item))
            elif item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif item.get("type") == "image":
                parts.append("[image]")
            else:
                parts.append(str(item))
    message = "\n".join(part for part in parts if part).strip()
    message = message or "MCP tool completed"
    if payload.get("isError"):
        return ToolResult.failure(message, data={"mcp": payload})
    return ToolResult.success(message, data={"mcp": payload})


def _invoke(
    client: StdioMCPClient,
    tool_name: str,
    **arguments: Any,
) -> ToolResult:
    try:
        payload = client.call_tool(tool_name, arguments)
    except MCPError as exc:
        return ToolResult.failure(str(exc))
    return _to_tool_result(payload)


class MCPManager:
    def __init__(self, servers: dict[str, MCPServerSettings] | None = None) -> None:
        self.servers = servers or {}
        self.clients: dict[str, StdioMCPClient] = {}
        self.registered_names: list[str] = []

    def start(self, registry: ToolRegistry | None = None) -> list[str]:
        self.close(registry)
        errors: list[str] = []
        for name, settings in self.servers.items():
            if not settings.enabled:
                continue
            if not settings.command:
                errors.append(f"{name}: no command configured")
                continue
            client = StdioMCPClient(
                settings.command,
                env=settings.env,
                timeout_seconds=settings.timeout_seconds,
                name=name,
            )
            try:
                client.start()
                client.initialize()
                client.list_tools()
            except Exception as exc:
                logger.warning("mcp[%s] failed: %s", name, exc)
                errors.append(f"{name}: {exc}")
                client.close()
                continue
            self.clients[name] = client
            if registry is not None:
                self._register_tools(name, client, registry)
        return errors

    def _register_tools(
        self,
        server_name: str,
        client: StdioMCPClient,
        registry: ToolRegistry,
    ) -> None:
        for tool in client.tools:
            tool_name = tool.get("name")
            if not isinstance(tool_name, str) or not tool_name:
                continue
            registered = _registered_name(server_name, tool_name)
            if registry.get(registered) is not None:
                continue
            annotations = tool.get("annotations")
            read_only = isinstance(annotations, dict) and bool(
                annotations.get("readOnlyHint")
            )
            level = ActionLevel.READ_ONLY if read_only else ActionLevel.SENSITIVE
            description = str(
                tool.get("description")
                or f"MCP tool {tool_name} from {server_name}"
            )
            registry.register(
                registered,
                description,
                level,
                partial(_invoke, client, tool_name),
                _parameters(tool.get("inputSchema")),
            )
            self.registered_names.append(registered)

    def close(self, registry: ToolRegistry | None = None) -> None:
        if registry is not None:
            for name in self.registered_names:
                registry.unregister(name)
        self.registered_names.clear()
        for client in self.clients.values():
            client.close()
        self.clients.clear()
