import unittest
from types import SimpleNamespace

from model import _api_token_measurement, _local_generation_was_truncated


class _Token(int):
    def item(self) -> int:
        return int(self)


class ModelTruncationTests(unittest.TestCase):
    def test_api_uses_length_finish_reason(self):
        completion = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="length")],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8),
        )

        measurement = _api_token_measurement(
            completion,
            "prompt",
            "output",
            max_output_tokens=8,
        )

        self.assertTrue(measurement.truncated)
        self.assertEqual(measurement.finish_reason, "length")
        self.assertEqual(measurement.max_output_tokens, 8)
        self.assertEqual(measurement.truncation_detection, "api_finish_reason")

    def test_api_stop_finish_reason_is_not_truncated(self):
        completion = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7),
        )

        measurement = _api_token_measurement(
            completion,
            "prompt",
            "output",
            max_output_tokens=8,
        )

        self.assertFalse(measurement.truncated)

    def test_local_output_at_limit_without_eos_is_truncated(self):
        truncated = _local_generation_was_truncated(
            [[_Token(1), _Token(2), _Token(3), _Token(4)]],
            max_new_tokens=4,
            eos_token_id=99,
        )

        self.assertTrue(truncated)

    def test_local_output_ending_with_eos_is_not_truncated(self):
        truncated = _local_generation_was_truncated(
            [[_Token(1), _Token(2), _Token(3), _Token(99)]],
            max_new_tokens=4,
            eos_token_id=99,
        )

        self.assertFalse(truncated)

    def test_local_output_below_limit_is_not_truncated(self):
        truncated = _local_generation_was_truncated(
            [[_Token(1), _Token(2), _Token(3)]],
            max_new_tokens=4,
            eos_token_id=99,
        )

        self.assertFalse(truncated)


if __name__ == "__main__":
    unittest.main()
