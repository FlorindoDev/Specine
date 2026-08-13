from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class GenerationContext:
    agent: str
    stage: str
    problem_id: str | int
    iteration: int | None = None


@dataclass(frozen=True)
class TokenMeasurement:
    input_tokens: int
    output_tokens: int
    source: str
    estimated: bool = False

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Token counts cannot be negative")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class TokenUsageRecorder:
    """Persists every LLM call and maintains run-level aggregates."""

    EVENTS_FILENAME = "token_usage.jsonl"
    SUMMARY_FILENAME = "token_usage_summary.json"

    def __init__(
        self,
        output_dir: str | Path,
        benchmark: str,
        model: str,
        variant: str,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self._output_dir / self.EVENTS_FILENAME
        self._summary_path = self._output_dir / self.SUMMARY_FILENAME
        self._metadata = {
            "benchmark": benchmark,
            "model": model,
            "variant": variant,
        }
        self._summary = self._new_summary()
        self._load_existing_events()
        self._write_summary()

    @property
    def events_path(self) -> Path:
        return self._events_path

    @property
    def summary_path(self) -> Path:
        return self._summary_path

    @property
    def summary(self) -> dict[str, Any]:
        return self._summary

    def record(
        self,
        context: GenerationContext,
        measurement: TokenMeasurement,
    ) -> None:
        event = {
            "call_id": str(uuid4()),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            **self._metadata,
            **asdict(context),
            **asdict(measurement),
            "total_tokens": measurement.total_tokens,
        }
        with self._events_path.open("a", encoding="utf-8") as events_file:
            events_file.write(json.dumps(event, ensure_ascii=False) + "\n")

        self._aggregate(event)
        self._write_summary()

    def _new_summary(self) -> dict[str, Any]:
        return {
            **self._metadata,
            "totals": self._new_bucket(),
            "agents": {},
            "iterations": {},
            "stages": {},
        }

    @staticmethod
    def _new_bucket() -> dict[str, int]:
        return {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_calls": 0,
        }

    def _load_existing_events(self) -> None:
        if not self._events_path.is_file():
            return

        with self._events_path.open("r", encoding="utf-8") as events_file:
            for line in events_file:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if all(event.get(key) == value for key, value in self._metadata.items()):
                    self._aggregate(event)

    def _aggregate(self, event: dict[str, Any]) -> None:
        self._add_to_bucket(self._summary["totals"], event)

        agent_bucket = self._summary["agents"].setdefault(
            event["agent"], self._new_bucket()
        )
        self._add_to_bucket(agent_bucket, event)

        iteration_key = (
            "initial" if event.get("iteration") is None else str(event["iteration"])
        )
        iteration = self._summary["iterations"].setdefault(
            iteration_key,
            {"totals": self._new_bucket(), "agents": {}},
        )
        self._add_to_bucket(iteration["totals"], event)
        iteration_agent = iteration["agents"].setdefault(
            event["agent"], self._new_bucket()
        )
        self._add_to_bucket(iteration_agent, event)

        stage_bucket = self._summary["stages"].setdefault(
            event["stage"], self._new_bucket()
        )
        self._add_to_bucket(stage_bucket, event)

    @staticmethod
    def _add_to_bucket(bucket: dict[str, int], event: dict[str, Any]) -> None:
        bucket["calls"] += 1
        bucket["input_tokens"] += int(event["input_tokens"])
        bucket["output_tokens"] += int(event["output_tokens"])
        bucket["total_tokens"] += int(event["total_tokens"])
        bucket["estimated_calls"] += int(bool(event.get("estimated", False)))

    def _write_summary(self) -> None:
        temporary_path = self._summary_path.with_suffix(".json.tmp")
        with temporary_path.open("w", encoding="utf-8") as summary_file:
            json.dump(self._summary, summary_file, ensure_ascii=False, indent=2)
        os.replace(temporary_path, self._summary_path)
