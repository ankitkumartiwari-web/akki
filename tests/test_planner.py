import unittest

from akki import planner
from akki.config import Config
from akki.models import ActionLevel, ActionRequest, ToolResult
from akki.registry import ToolRegistry


class PlannerTests(unittest.TestCase):
    def test_split_steps_uses_explicit_connectors(self) -> None:
        self.assertEqual(
            planner.split_steps("open notepad then take a screenshot"),
            ["open notepad", "take a screenshot"],
        )
        self.assertEqual(
            planner.split_steps("open notepad and calculator"),
            ["open notepad and calculator"],
        )

    def test_plan_steps_routes_each_step(self) -> None:
        requests = planner.plan_steps(
            "open notepad then take a screenshot",
            Config.default(),
        )
        self.assertEqual([request.tool for request in requests], ["launch_app", "screenshot"])

    def test_plan_steps_requires_every_step_to_route(self) -> None:
        self.assertEqual(
            planner.plan_steps(
                "open notepad then frobnicate the widget",
                Config.default(),
            ),
            [],
        )

    def test_execute_steps_stops_after_failure(self) -> None:
        calls: list[str] = []
        registry = ToolRegistry()
        registry.register(
            "first",
            "first step",
            ActionLevel.READ_ONLY,
            lambda: calls.append("first") or ToolResult.success("first ok"),
        )
        registry.register(
            "boom",
            "failing step",
            ActionLevel.READ_ONLY,
            lambda: calls.append("boom") or ToolResult.failure("boom failed"),
        )
        registry.register(
            "last",
            "last step",
            ActionLevel.READ_ONLY,
            lambda: calls.append("last") or ToolResult.success("last ok"),
        )
        result = planner.execute_steps(
            [
                ActionRequest("first", {}),
                ActionRequest("boom", {}),
                ActionRequest("last", {}),
            ],
            registry,
            confirm=lambda _: True,
        )
        self.assertFalse(result.ok)
        self.assertEqual(calls, ["first", "boom"])
        self.assertIn("boom failed", result.message)
        self.assertEqual(len(result.data["steps"]), 2)


if __name__ == "__main__":
    unittest.main()
