import unittest

from odin.models import ActionLevel, ActionRequest, ToolResult
from odin.permissions import requires_confirmation
from odin.registry import ToolRegistry


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

    def test_exception_is_reported(self) -> None:
        def boom(value: str) -> ToolResult:
            raise RuntimeError("exploded")

        self.registry.register("boom", "boom", ActionLevel.READ_ONLY, boom, {"value": "text"})
        result = self.registry.execute(ActionRequest("boom", {"value": "x"}))
        self.assertFalse(result.ok)
        self.assertIn("exploded", result.message)


if __name__ == "__main__":
    unittest.main()
