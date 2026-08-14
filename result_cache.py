import hashlib
import json
import re
from pathlib import Path


_CACHE_METADATA_VERSION = 1
_MAX_MODEL_SLUG_LENGTH = 80


def model_result_namespace(
    configured_model: str,
    effective_model: str,
) -> str:
    """Return stable result directory name without losing model identity."""

    if configured_model == effective_model:
        return configured_model

    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", effective_model).strip("._-")
    slug = (slug or "model")[:_MAX_MODEL_SLUG_LENGTH]
    identity_hash = hashlib.sha256(effective_model.encode("utf-8")).hexdigest()[:12]
    return f"{configured_model}__{slug}__{identity_hash}"


def cache_matches_model(
    metadata_path: str | Path,
    configured_model: str,
    effective_model: str,
) -> bool:
    try:
        with Path(metadata_path).open("r", encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
    except (OSError, json.JSONDecodeError, TypeError):
        return False

    return metadata == _cache_metadata(configured_model, effective_model)


def save_cache_metadata(
    metadata_path: str | Path,
    configured_model: str,
    effective_model: str,
) -> None:
    path = Path(metadata_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as metadata_file:
        json.dump(
            _cache_metadata(configured_model, effective_model),
            metadata_file,
            ensure_ascii=False,
            indent=2,
        )


def _cache_metadata(configured_model: str, effective_model: str) -> dict[str, object]:
    return {
        "version": _CACHE_METADATA_VERSION,
        "configured_model": configured_model,
        "effective_model": effective_model,
    }
