import tempfile
import unittest

from token_usage import (
    GenerationContext,
    TokenMeasurement,
    TokenUsageRecorder,
    load_truncation_report,
)


class TokenUsageRecorderTests(unittest.TestCase):
    def test_records_and_aggregates_truncation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = TokenUsageRecorder(
                temp_dir,
                benchmark="apps-eval",
                model="test-model",
                variant="A",
            )
            context = GenerationContext(
                agent="Architect",
                stage="initial_code",
                problem_id="problem-1",
                iteration=None,
            )
            recorder.record(
                context,
                TokenMeasurement(
                    input_tokens=100,
                    output_tokens=512,
                    source="api_usage",
                    max_output_tokens=512,
                    finish_reason="length",
                    truncated=True,
                    truncation_detection="api_finish_reason",
                ),
            )
            recorder.record(
                context,
                TokenMeasurement(
                    input_tokens=100,
                    output_tokens=200,
                    source="api_usage",
                    max_output_tokens=512,
                    finish_reason="stop",
                    truncated=False,
                    truncation_detection="api_finish_reason",
                ),
            )

            truncation = load_truncation_report(temp_dir)

        totals = recorder.summary["totals"]
        self.assertEqual(totals["truncation_analyzed_calls"], 2)
        self.assertEqual(totals["truncated_calls"], 1)
        self.assertIsNotNone(truncation)
        assert truncation is not None
        self.assertEqual(truncation.stats.truncated_response_percent, 50.0)

    def test_rejects_invalid_output_limit(self):
        with self.assertRaisesRegex(ValueError, "greater than 0"):
            TokenMeasurement(
                input_tokens=1,
                output_tokens=1,
                source="test",
                max_output_tokens=0,
            )


if __name__ == "__main__":
    unittest.main()
