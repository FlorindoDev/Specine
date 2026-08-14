import json
import tempfile
import unittest
from pathlib import Path

from result_cache import (
    cache_matches_model,
    model_result_namespace,
    save_cache_metadata,
)


class ModelResultNamespaceTests(unittest.TestCase):
    def test_fixed_model_keeps_existing_namespace(self):
        self.assertEqual(
            model_result_namespace("gpt-4o-mini-2024-07-18", "gpt-4o-mini-2024-07-18"),
            "gpt-4o-mini-2024-07-18",
        )

    def test_openrouter_models_get_distinct_safe_namespaces(self):
        first = model_result_namespace("openrouter", "openai/gpt-4o-mini")
        second = model_result_namespace("openrouter", "google/gemini-2.5-flash")

        self.assertNotEqual(first, second)
        self.assertNotIn("/", first)
        self.assertNotIn("/", second)
        self.assertTrue(first.startswith("openrouter__openai_gpt-4o-mini__"))


class CacheMetadataTests(unittest.TestCase):
    def test_cache_requires_matching_effective_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_path = Path(temp_dir) / "problem_code.metadata.json"
            save_cache_metadata(
                metadata_path,
                configured_model="openrouter",
                effective_model="openai/gpt-4o-mini",
            )

            self.assertTrue(cache_matches_model(
                metadata_path,
                configured_model="openrouter",
                effective_model="openai/gpt-4o-mini",
            ))
            self.assertFalse(cache_matches_model(
                metadata_path,
                configured_model="openrouter",
                effective_model="anthropic/claude-sonnet-4",
            ))

    def test_missing_or_incomplete_metadata_is_not_compatible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_path = Path(temp_dir) / "problem_code.metadata.json"
            self.assertFalse(cache_matches_model(
                metadata_path,
                configured_model="openrouter",
                effective_model="openai/gpt-4o-mini",
            ))

            metadata_path.write_text(
                json.dumps({"configured_model": "openrouter"}),
                encoding="utf-8",
            )
            self.assertFalse(cache_matches_model(
                metadata_path,
                configured_model="openrouter",
                effective_model="openai/gpt-4o-mini",
            ))


if __name__ == "__main__":
    unittest.main()
