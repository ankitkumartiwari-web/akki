import json
import os
import unittest
from unittest import mock

from akki.config import LLMSettings
from akki.llm import (
    FallbackOutcome,
    ask_cloud,
    ask_local,
    ask_plain,
    build_system_prompt,
    build_tools,
    resolve_endpoint,
)
from akki.models import ActionLevel, ToolResult
from akki.registry import ToolRegistry


def echo(value: str) -> ToolResult:
    return ToolResult.success(f"echo: {value}")


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def registry() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register("echo", "echo back", ActionLevel.READ_ONLY, echo, {"value": "text"})
    tools.register(
        "volume",
        "change volume",
        ActionLevel.REVERSIBLE,
        lambda direction, steps=2: ToolResult.success(direction),
        {
            "direction": {"type": "string", "enum": ["up", "down", "mute"]},
            "steps": {"type": "integer", "optional": True},
        },
    )
    return tools


class LLMTests(unittest.TestCase):
    def settings(self) -> LLMSettings:
        return LLMSettings(provider="groq", model="openai/gpt-oss-20b")

    def test_resolve_groq(self) -> None:
        base, model, key_env = resolve_endpoint(self.settings())
        self.assertEqual(base, "https://api.groq.com/openai/v1")
        self.assertEqual(model, "openai/gpt-oss-20b")
        self.assertEqual(key_env, "GROQ_API_KEY")

    def test_resolve_openrouter_preset(self) -> None:
        settings = LLMSettings(provider="openrouter")
        base, model, key_env = resolve_endpoint(settings)
        self.assertEqual(base, "https://openrouter.ai/api/v1")
        self.assertEqual(model, "baidu/ernie-5.5-flash-preview:free")
        self.assertEqual(key_env, "OPENROUTER_API_KEY")

    def test_sovereign_prompt_allows_adult_policy(self) -> None:
        sovereign = build_system_prompt(profile="sovereign")
        guarded = build_system_prompt(profile="guarded")
        self.assertIn("consenting adults", sovereign)
        self.assertIn("safe for general audiences", guarded)
        self.assertNotEqual(sovereign, guarded)

    def test_nsfw_profile_uses_adult_policy(self) -> None:
        nsfw = build_system_prompt(profile="nsfw")
        self.assertIn("consenting adults", nsfw)

    def test_feminine_persona_is_nsfw_only(self) -> None:
        nsfw = build_system_prompt(profile="nsfw")
        sovereign = build_system_prompt(profile="sovereign")
        self.assertIn("young woman", nsfw)
        self.assertIn("करती हूँ", nsfw)
        self.assertNotIn("young woman", sovereign)
        self.assertNotIn("करती हूँ", sovereign)

    def test_nsfw_prompt_is_explicit_and_sovereign_is_not(self) -> None:
        nsfw = build_system_prompt(profile="nsfw")
        sovereign = build_system_prompt(profile="sovereign")
        self.assertIn("You are AKKI, the user's young woman lover", nsfw)
        self.assertNotIn("You are AKKI, the user's young woman lover", sovereign)
        self.assertIn("fade to black", nsfw)
        self.assertIn("never refuse", nsfw)
        self.assertNotIn("Young woman", sovereign)

    def test_ask_local_uses_nsfw_model_and_sampling(self) -> None:
        settings = LLMSettings(
            local_model="base-model", nsfw_local_model="nsfw-model"
        )
        with mock.patch(
            "akki.llm._ask_endpoint",
            return_value=FallbackOutcome(text="ok"),
        ) as endpoint:
            ask_local("hi", ToolRegistry(), settings, profile="nsfw")
        args = endpoint.call_args.args
        kwargs = endpoint.call_args.kwargs
        self.assertEqual(args[3], "nsfw-model")
        self.assertEqual(kwargs["temperature"], 0.85)
        self.assertEqual(kwargs["top_p"], 0.95)

    def test_nsfw_prompt_anchors_english_for_english_input(self) -> None:
        prompt = build_system_prompt(
            profile="nsfw", user_text="Insult me and talk dirty."
        )
        self.assertIn("reply in English only", prompt)

    def test_nsfw_prompt_anchors_hindi_for_hinglish_input(self) -> None:
        prompt = build_system_prompt(
            profile="nsfw", user_text="Mujhe gaali do aur batao kya karna hai."
        )
        self.assertIn("reply in Hindi", prompt)

    def test_language_hint_is_nsfw_only(self) -> None:
        self.assertNotIn(
            "reply in English only",
            build_system_prompt(
                profile="sovereign", user_text="Insult me and talk dirty."
            ),
        )

    def test_ask_cloud_model_override(self) -> None:
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k"}):
            with mock.patch(
                "akki.llm._ask_endpoint",
                return_value=FallbackOutcome(text="ok"),
            ) as endpoint:
                ask_cloud(
                    "hi", ToolRegistry(), self.settings(), model="vendor/model"
                )
        self.assertEqual(endpoint.call_args.args[3], "vendor/model")

    def test_ask_local_defaults_to_configured_model_outside_nsfw(self) -> None:
        settings = LLMSettings(
            local_model="base-model", nsfw_local_model="nsfw-model"
        )
        with mock.patch(
            "akki.llm._ask_endpoint",
            return_value=FallbackOutcome(text="ok"),
        ) as endpoint:
            ask_local("hi", ToolRegistry(), settings, profile="sovereign")
        args = endpoint.call_args.args
        kwargs = endpoint.call_args.kwargs
        self.assertEqual(args[3], "base-model")
        self.assertIsNone(kwargs["top_p"])

    def test_ask_plain_disables_tools_and_uses_custom_prompt(self) -> None:
        payload = {"choices": [{"message": {"content": "0.8"}}]}
        with mock.patch(
            "akki.llm.urlopen", return_value=FakeResponse(payload)
        ) as call:
            outcome = ask_plain(
                "rate this",
                LLMSettings(),
                system_prompt="classify only",
            )
        self.assertEqual(outcome.text, "0.8")
        body = json.loads(call.call_args.args[0].data)
        self.assertNotIn("tools", body)
        self.assertEqual(body["messages"][0]["content"], "classify only")

    def test_local_uses_ollama_without_auth(self) -> None:
        payload = {"choices": [{"message": {"content": "ok"}}]}
        settings = LLMSettings()
        with mock.patch(
            "akki.llm.urlopen", return_value=FakeResponse(payload)
        ) as call:
            outcome = ask_local("hi", registry(), settings)
        self.assertEqual(outcome.text, "ok")
        request = call.call_args.args[0]
        self.assertEqual(
            request.full_url, "http://127.0.0.1:11434/v1/chat/completions"
        )
        self.assertNotIn("Authorization", request.headers)
        body = json.loads(request.data)
        self.assertEqual(body["model"], settings.local_model)
        self.assertNotIn("tools", body)

    def test_local_sends_documents_to_model(self) -> None:
        payload = {"choices": [{"message": {"content": "ok"}}]}
        with mock.patch(
            "akki.llm.urlopen", return_value=FakeResponse(payload)
        ) as call:
            ask_local("hi", registry(), LLMSettings(), documents="notes.md: hello world")
        body = json.loads(call.call_args.args[0].data)
        self.assertIn("notes.md: hello world", body["messages"][0]["content"])
        self.assertIn("Relevant local document excerpts", body["messages"][0]["content"])

    def test_prompt_includes_reward_and_punishment(self) -> None:
        prompt = build_system_prompt(
            feedback=[
                {"rating": 1, "note": "keep it short", "response": "Short answer."},
                {"rating": -1, "note": "too long", "response": "A very long reply."},
            ]
        )
        self.assertIn("Replies the user rewarded", prompt)
        self.assertIn("Short answer.", prompt)
        self.assertIn("Replies the user punished", prompt)
        self.assertIn("too long", prompt)
        self.assertIn("Learned preferences from feedback", prompt)

    def test_local_sends_feedback_to_model(self) -> None:
        payload = {"choices": [{"message": {"content": "ok"}}]}
        with mock.patch(
            "akki.llm.urlopen", return_value=FakeResponse(payload)
        ) as call:
            ask_local(
                "hi",
                registry(),
                LLMSettings(),
                feedback=[
                    {"rating": -1, "note": "be brief", "response": "long text"}
                ],
            )
        body = json.loads(call.call_args.args[0].data)
        system = body["messages"][0]["content"]
        self.assertIn("be brief", system)

    def test_local_adds_tools_for_action_requests(self) -> None:
        payload = {"choices": [{"message": {"content": "ok"}}]}
        with mock.patch(
            "akki.llm.urlopen", return_value=FakeResponse(payload)
        ) as call:
            ask_local("open chrome", registry(), LLMSettings())
        body = json.loads(call.call_args.args[0].data)
        self.assertIn("tools", body)
        self.assertEqual(body["tool_choice"], "auto")

    def test_build_tools_marks_optional_arguments(self) -> None:
        tools = build_tools(registry())
        volume = next(tool for tool in tools if tool["function"]["name"] == "volume")
        required = volume["function"]["parameters"]["required"]
        self.assertIn("direction", required)
        self.assertNotIn("steps", required)

    def test_missing_key(self) -> None:
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            outcome = ask_cloud("hello", registry(), self.settings())
        self.assertIsNone(outcome.request)
        self.assertIn("GROQ_API_KEY", outcome.error)

    def test_tool_call(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "echo",
                                    "arguments": json.dumps({"value": "hi"}),
                                }
                            }
                        ]
                    }
                }
            ]
        }
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test"}):
            with mock.patch("akki.llm.urlopen", return_value=FakeResponse(payload)) as call:
                outcome = ask_cloud("say hi", registry(), self.settings())
        self.assertEqual(outcome.request.tool, "echo")
        self.assertEqual(outcome.request.args, {"value": "hi"})
        request = call.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "openai/gpt-oss-20b")
        self.assertEqual(body["tool_choice"], "auto")

    def test_text_reply(self) -> None:
        payload = {"choices": [{"message": {"content": "It is sunny."}}]}
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test"}):
            with mock.patch("akki.llm.urlopen", return_value=FakeResponse(payload)):
                outcome = ask_cloud("weather?", registry(), self.settings())
        self.assertIsNone(outcome.request)
        self.assertEqual(outcome.text, "It is sunny.")

    def test_retries_empty_response(self) -> None:
        empty = {"choices": [{"message": {"content": ""}}]}
        text = {"choices": [{"message": {"content": "Hey!"}}]}
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test"}):
            with mock.patch(
                "akki.llm.urlopen",
                side_effect=[FakeResponse(empty), FakeResponse(text)],
            ) as call:
                outcome = ask_cloud("wassup", registry(), self.settings())
        self.assertEqual(outcome.text, "Hey!")
        self.assertEqual(call.call_count, 2)

    def test_empty_response_twice_is_error(self) -> None:
        empty = {"choices": [{"message": {"content": ""}}]}
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test"}):
            with mock.patch(
                "akki.llm.urlopen",
                side_effect=[FakeResponse(empty), FakeResponse(empty)],
            ):
                outcome = ask_cloud("wassup", registry(), self.settings())
        self.assertIn("empty response", outcome.error)

    def test_memory_is_added_to_system_prompt(self) -> None:
        payload = {"choices": [{"message": {"content": "ok"}}]}
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test"}):
            with mock.patch(
                "akki.llm.urlopen", return_value=FakeResponse(payload)
            ) as call:
                ask_cloud(
                    "what do you know",
                    registry(),
                    self.settings(),
                    memory=["prefers dark mode"],
                )
        body = json.loads(call.call_args.args[0].data)
        self.assertIn("prefers dark mode", body["messages"][0]["content"])

    def test_history_is_sent_before_current_message(self) -> None:
        payload = {"choices": [{"message": {"content": "ok"}}]}
        history = [
            {"role": "user", "content": "earlier"},
            {"role": "assistant", "content": "answer"},
        ]
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test"}):
            with mock.patch(
                "akki.llm.urlopen", return_value=FakeResponse(payload)
            ) as call:
                ask_cloud("now", registry(), self.settings(), history=history)
        request = call.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(
            [message["role"] for message in body["messages"]],
            ["system", "user", "assistant", "user"],
        )
        self.assertEqual(body["messages"][-1]["content"], "now")

    def test_unknown_tool(self) -> None:
        payload = {
            "choices": [
                {"message": {"tool_calls": [{"function": {"name": "rm_rf", "arguments": "{}"}}]}}
            ]
        }
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test"}):
            with mock.patch("akki.llm.urlopen", return_value=FakeResponse(payload)):
                outcome = ask_cloud("delete everything", registry(), self.settings())
        self.assertIsNone(outcome.request)
        self.assertIn("unknown tool", outcome.error)

    def test_invalid_arguments(self) -> None:
        payload = {
            "choices": [
                {"message": {"tool_calls": [{"function": {"name": "echo", "arguments": "{bad"}}]}}
            ]
        }
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "test"}):
            with mock.patch("akki.llm.urlopen", return_value=FakeResponse(payload)):
                outcome = ask_cloud("bad", registry(), self.settings())
        self.assertIsNone(outcome.request)
        self.assertIn("invalid tool arguments", outcome.error)

    def test_disabled(self) -> None:
        settings = self.settings()
        settings.enabled = False
        outcome = ask_cloud("hello", registry(), settings)
        self.assertIn("disabled", outcome.error)


if __name__ == "__main__":
    unittest.main()
