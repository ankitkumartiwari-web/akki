import sys
import tempfile
import unittest
from pathlib import Path

from akki.config import MCPServerSettings
from akki.mcp import MCPManager, StdioMCPClient
from akki.models import ActionRequest
from akki.registry import ToolRegistry

SERVER = '''
import json
import sys

for line in sys.stdin:
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        continue
    if "id" not in message:
        continue
    method = message.get("method")
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake", "version": "1"},
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": "echo",
                    "description": "Echo text",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"text": {"type": "string", "description": "text"}},
                    },
                    "annotations": {"readOnlyHint": True},
                }
            ]
        }
    elif method == "tools/call":
        arguments = (message.get("params") or {}).get("arguments") or {}
        result = {
            "content": [
                {"type": "text", "text": "echo:" + str(arguments.get("text", ""))}
            ]
        }
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\\n")
    sys.stdout.flush()
'''


class MCPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.script = Path(self.temp.name) / "fake_mcp.py"
        self.script.write_text(SERVER, encoding="utf-8")
        self.command = [sys.executable, str(self.script)]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_stdio_client(self) -> None:
        client = StdioMCPClient(self.command, timeout_seconds=5, name="fake")
        try:
            client.start()
            info = client.initialize()
            self.assertEqual(info["serverInfo"]["name"], "fake")
            tools = client.list_tools()
            self.assertEqual(tools[0]["name"], "echo")
            result = client.call_tool("echo", {"text": "hello"})
            self.assertEqual(result["content"][0]["text"], "echo:hello")
        finally:
            client.close()

    def test_manager_registers_and_invokes(self) -> None:
        registry = ToolRegistry()
        manager = MCPManager(
            {
                "fake": MCPServerSettings(
                    command=self.command,
                    timeout_seconds=5,
                )
            }
        )
        try:
            errors = manager.start(registry)
            self.assertEqual(errors, [])
            self.assertIn("mcp_fake_echo", manager.registered_names)
            spec = registry.get("mcp_fake_echo")
            self.assertIsNotNone(spec)
            result = registry.execute(
                ActionRequest("mcp_fake_echo", {"text": "hi"}),
                confirm=lambda _: True,
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.message, "echo:hi")
        finally:
            manager.close(registry)
        self.assertIsNone(registry.get("mcp_fake_echo"))


if __name__ == "__main__":
    unittest.main()
