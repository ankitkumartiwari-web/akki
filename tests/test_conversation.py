import unittest

from akki.conversation import Conversation, resolve_followup
from akki.models import ActionRequest, ToolResult


class ConversationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conversation = Conversation()

    def test_repeat_last_request(self) -> None:
        request = ActionRequest("web_search", {"query": "python"})
        self.conversation.record(request, ToolResult.success("ok"))
        again = resolve_followup("do that again", self.conversation)
        self.assertEqual(again, request)

    def test_open_it_uses_last_match(self) -> None:
        request = ActionRequest("find_files", {"query": "akki"})
        result = ToolResult.success("found", data={"matches": ["C:\\akki\\doc.md"]})
        self.conversation.record(request, result)
        follow = resolve_followup("open it", self.conversation)
        self.assertIsNotNone(follow)
        self.assertEqual(follow.tool, "open_path")
        self.assertEqual(follow.args, {"path": "C:\\akki\\doc.md"})

    def test_open_it_in_app(self) -> None:
        result = ToolResult.success("found", data={"matches": ["C:\\akki\\doc.md"]})
        self.conversation.record(ActionRequest("find_files", {"query": "akki"}), result)
        follow = resolve_followup("open it in the code editor", self.conversation)
        self.assertIsNotNone(follow)
        self.assertEqual(follow.tool, "open_in_app")
        self.assertEqual(follow.args["alias"], "code editor")

    def test_search_for_it_repeats_query(self) -> None:
        request = ActionRequest("web_search", {"query": "weather"})
        self.conversation.record(request, ToolResult.success("ok"))
        follow = resolve_followup("search for it", self.conversation)
        self.assertEqual(follow, request)

    def test_last_exchange_returns_latest_pair(self) -> None:
        self.conversation.add("user", "first question")
        self.conversation.add("assistant", "first answer")
        self.conversation.add("user", "second question")
        self.conversation.add("assistant", "second answer")
        self.assertEqual(
            self.conversation.last_exchange(),
            ("second question", "second answer"),
        )

    def test_no_followup_without_state(self) -> None:
        self.assertIsNone(resolve_followup("open it", self.conversation))
        self.assertIsNone(resolve_followup("do that again", self.conversation))

    def test_cloud_messages_are_bounded(self) -> None:
        conversation = Conversation(cloud_turns=3, max_chars=10)
        for index in range(5):
            conversation.add("user", f"question {index}")
            conversation.add("assistant", f"answer {index}")
        messages = conversation.cloud_messages()
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[-1]["content"], "answer 4")
        self.assertTrue(all(len(m["content"]) <= 10 for m in messages))

    def test_cloud_messages_respect_char_budget(self) -> None:
        conversation = Conversation(
            cloud_turns=20, max_chars=100, max_history_chars=30
        )
        conversation.add("user", "a" * 20)
        conversation.add("assistant", "b" * 20)
        conversation.add("user", "c" * 20)
        messages = conversation.cloud_messages()
        self.assertEqual(messages[-1]["content"], "c" * 20)
        self.assertLessEqual(sum(len(m["content"]) for m in messages), 30)

    def test_on_turn_callback_receives_turns(self) -> None:
        seen: list[tuple[str, str]] = []
        conversation = Conversation(on_turn=lambda role, text: seen.append((role, text)))
        conversation.add("user", "hi")
        conversation.add("assistant", "hello")
        self.assertEqual(seen, [("user", "hi"), ("assistant", "hello")])

    def test_clear_resets_state(self) -> None:
        self.conversation.record(
            ActionRequest("web_search", {"query": "x"}), ToolResult.success("ok")
        )
        self.conversation.add("user", "hi")
        self.conversation.clear()
        self.assertEqual(self.conversation.cloud_messages(), [])
        self.assertIsNone(resolve_followup("do that again", self.conversation))
