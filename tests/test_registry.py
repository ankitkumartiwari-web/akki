import unittest

from akki.models import ActionLevel, ActionRequest, ToolResult
from akki.permissions import requires_confirmation
from akki.registry import ToolRegistry


def echo(value: str) -> ToolResult:
    return ToolResult.success(f"echo: {value}")


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()

    def test_execute_tool(self) -> None:
        self.registry.register("echo", "echo", ActionLevel.READ_ONLY, echo, {"value": "text"})
        result = self.registry.execute(ActionRequest("echo", {"value": "hello"}))
        self.assertTrue(result.ok)
        self.assertEqual(result.message, "echo: hello")

    def test_unknown_tool(self) -> None:
        result = self.registry.execute(ActionRequest("missing", {}))
        self.assertFalse(result.ok)
        self.assertIn("unknown tool", result.message)

    def test_invalid_arguments(self) -> None:
        self.registry.register("echo", "echo", ActionLevel.READ_ONLY, echo, {"value": "text"})
        result = self.registry.execute(ActionRequest("echo", {"other": "x"}))
        self.assertFalse(result.ok)
        self.assertIn("invalid arguments", result.message)

    def test_confirmation_required(self) -> None:
        self.registry.register("echo", "echo", ActionLevel.SENSITIVE, echo, {"value": "text"})
        result = self.registry.execute(ActionRequest("echo", {"value": "x"}))
        self.assertFalse(result.ok)
        self.assertIn("requires confirmation", result.message)

    def test_confirmation_denied(self) -> None:
        self.registry.register("echo", "echo", ActionLevel.SENSITIVE, echo, {"value": "text"})
        result = self.registry.execute(
            ActionRequest("echo", {"value": "x"}), confirm=lambda prompt: False
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "cancelled by user")

    def test_confirmation_granted(self) -> None:
        self.registry.register("echo", "echo", ActionLevel.SENSITIVE, echo, {"value": "text"})
        result = self.registry.execute(
            ActionRequest("echo", {"value": "x"}), confirm=lambda prompt: True
        )
        self.assertTrue(result.ok)

    def test_guarded_requires_confirmation_for_reversible(self) -> None:
        self.assertTrue(requires_confirmation(ActionLevel.REVERSIBLE, "guarded"))
        self.assertFalse(requires_confirmation(ActionLevel.REVERSIBLE, "sovereign"))

    def test_nsfw_blocks_web_search_and_open_url(self) -> None:
        calls = []
        self.registry.register(
            "web_search",
            "search",
            ActionLevel.READ_ONLY,
            lambda query: calls.append(query) or ToolResult.success("searched"),
        )
        self.registry.register(
            "open_url",
            "open",
            ActionLevel.READ_ONLY,
            lambda url: calls.append(url) or ToolResult.success("opened"),
        )
        search = self.registry.execute(
            ActionRequest("web_search", {"query": "x"}), profile="nsfw"
        )
        opened = self.registry.execute(
            ActionRequest("open_url", {"url": "https://google.com"}), profile="nsfw"
        )
        self.assertFalse(search.ok)
        self.assertFalse(opened.ok)
        self.assertEqual(calls, [])
        allowed = self.registry.execute(
            ActionRequest("web_search", {"query": "x"}), profile="sovereign"
        )
        self.assertTrue(allowed.ok)

    def test_exception_is_reported(self) -> None:
        def boom(value: str) -> ToolResult:
            raise RuntimeError("exploded")

        self.registry.register("boom", "boom", ActionLevel.READ_ONLY, boom, {"value": "text"})
        result = self.registry.execute(ActionRequest("boom", {"value": "x"}))
        self.assertFalse(result.ok)
        self.assertIn("exploded", result.message)


if __name__ == "__main__":
    unittest.main()
