import unittest
from unittest.mock import patch

from vga.llm import InfraError, LlmConfig, chat_json, chat_text, extract_json, stage_config


CONFIG = LlmConfig("openai", "test/model", "key", "https://example.test/v1")


class ExtractJsonTests(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_object(self):
        raw = "Sure thing:\n```json\n{\"a\": [1, 2]}\n```\nDone."
        self.assertEqual(extract_json(raw), {"a": [1, 2]})

    def test_extract_json_from_prose(self):
        self.assertEqual(extract_json('prefix {"b": null} suffix'), {"b": None})

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            extract_json("no json in here")


class ChatJsonLoopTests(unittest.TestCase):
    def test_passes_on_first_valid_response(self):
        with patch("vga.llm._post", return_value=_reply('{"a": 1}')) as post:
            value = chat_json(CONFIG, [], lambda data: data)
        self.assertEqual(value, {"a": 1})
        self.assertEqual(post.call_count, 1)

    def test_repairs_once_with_feedback(self):
        responses = [_reply("not json at all"), _reply('{"fixed": true}')]
        with patch("vga.llm._post", side_effect=responses) as post:
            value = chat_json(CONFIG, [], lambda data: data)
        self.assertEqual(value, {"fixed": True})
        self.assertEqual(post.call_count, 2)

    def test_raises_after_attempts(self):
        with patch("vga.llm._post", return_value=_reply("still not json")):
            with self.assertRaises(RuntimeError):
                chat_json(CONFIG, [], lambda data: data, attempts=2)


class StageRoutingTests(unittest.TestCase):
    def test_override_only_changes_the_model(self):
        routed = stage_config(CONFIG, "VGA_CODEGEN_MODEL", {"VGA_CODEGEN_MODEL": "strong/model"})
        self.assertEqual(routed.model, "strong/model")
        self.assertEqual(routed.api_key, CONFIG.api_key)
        self.assertEqual(routed.base_url, CONFIG.base_url)

    def test_no_override_returns_the_same_config(self):
        self.assertIs(stage_config(CONFIG, "VGA_REVIEW_MODEL", {}), CONFIG)


class TransientHttpTests(unittest.TestCase):
    def test_retries_a_transient_upstream_error(self):
        responses = [RuntimeError("LLM 503: busy"), _reply('{"ok": true}')]
        with patch("vga.llm._post", side_effect=responses) as post, \
                patch("vga.llm.time.sleep", lambda _s: None):
            value = chat_json(CONFIG, [], lambda data: data)
        self.assertEqual(value, {"ok": True})
        self.assertEqual(post.call_count, 2)

    def test_does_not_retry_a_bad_key_or_request(self):
        for message in ("LLM 401: unauthorized", "LLM 400: bad request"):
            with self.subTest(message), patch("vga.llm._post", side_effect=RuntimeError(message)) as post:
                with self.assertRaises(RuntimeError):
                    chat_json(CONFIG, [], lambda data: data)
                self.assertEqual(post.call_count, 1)


class ChatTextLoopTests(unittest.TestCase):
    def test_failed_typecheck_feeds_back_the_errors(self):
        responses = [_reply("BAD CODE"), _reply("GOOD CODE")]
        checks = iter([ValueError("line 1: missing semicolon"), None])

        def validate(source: str) -> str:
            failure = next(checks)
            if failure:
                raise failure
            return source

        with patch("vga.llm._post", side_effect=responses) as post:
            value = chat_text(CONFIG, [], validate, attempts=2)
        self.assertEqual(value, "GOOD CODE")
        self.assertEqual(post.call_count, 2)

    def test_infra_errors_abort_instead_of_repairing(self):
        with patch("vga.llm._post", return_value=_reply("GOOD")) as post:
            with self.assertRaises(InfraError):
                chat_text(CONFIG, [], _raise_infra, attempts=3)
        self.assertEqual(post.call_count, 1)  # no wasted repair rounds


def _raise_infra(source: str) -> str:
    raise InfraError("render service unavailable")


def _reply(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


if __name__ == "__main__":
    unittest.main()


class TruncationRepairTests(unittest.TestCase):
    def test_truncated_code_gets_a_compact_rewrite_without_accepting_partial_output(self):
        truncated = _reply('incomplete file')
        truncated['choices'][0]['finish_reason'] = 'length'
        with patch('vga.llm._post', side_effect=[truncated, _reply('COMPLETE')]) as post:
            self.assertEqual(chat_text(CONFIG, [], lambda value: value, attempts=2), 'COMPLETE')
        self.assertIn('more compact', post.call_args_list[1].args[1]['messages'][-1]['content'])

    def test_empty_truncated_output_is_also_repaired(self):
        truncated = _reply('')
        truncated['choices'][0]['finish_reason'] = 'length'
        with patch('vga.llm._post', side_effect=[truncated, _reply('COMPLETE')]):
            self.assertEqual(chat_text(CONFIG, [], lambda value: value, attempts=2), 'COMPLETE')

    def test_sonnet_reasoning_leaves_room_for_scene_code(self):
        from dataclasses import replace
        config = replace(CONFIG, model='anthropic/claude-sonnet-5.5', base_url='https://openrouter.ai/api/v1')
        with patch('vga.llm._post', return_value=_reply('COMPLETE')) as post:
            chat_text(config, [], lambda value: value)
        self.assertEqual(post.call_args.args[1]['reasoning']['effort'], 'medium')
