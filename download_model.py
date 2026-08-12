#!/usr/bin/env python3
"""Download the default DeepSeek model used by the benchmarks."""

import sys
from pathlib import Path


MODEL_REPOSITORY = "deepseek-ai/deepseek-coder-7b-instruct-v1.5"
PROJECT_ROOT = Path(__file__).resolve().parent
MODEL_DIRECTORY = PROJECT_ROOT / "LLMs" / "deepseek-coder-7b-instruct-v1.5"


def download_model() -> Path:
    """Download the model snapshot and return its local directory."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise RuntimeError(
            "Dipendenza mancante. Attiva l'ambiente virtuale ed esegui "
            "'python -m pip install -r requirements.txt'."
        ) from error

    print(f"Download di {MODEL_REPOSITORY}")
    print(f"Destinazione: {MODEL_DIRECTORY}")
    MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)

    try:
        snapshot_download(
            repo_id=MODEL_REPOSITORY,
            local_dir=str(MODEL_DIRECTORY),
        )
    except Exception as error:
        raise RuntimeError(f"Download del modello non riuscito: {error}") from error

    if not (MODEL_DIRECTORY / "config.json").is_file():
        raise RuntimeError("Download incompleto: config.json non trovato.")

    return MODEL_DIRECTORY


def main() -> int:
    try:
        destination = download_model()
    except (OSError, RuntimeError) as error:
        print(f"Errore: {error}", file=sys.stderr)
        return 1

    print(f"Modello pronto in: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
