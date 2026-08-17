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
    max_output_tokens: int | None = None
    finish_reason: str | None = None
    truncated: bool | None = None
    truncation_detection: str | None = None

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Token counts cannot be negative")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than 0")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class AgentTokenUsage:
    agent: str
    total_tokens: int


@dataclass(frozen=True)
class IterationTokenUsage:
    iteration: int | None
    file_iteration_index: int | None
    total_tokens: int
    agents: tuple[AgentTokenUsage, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": "initial" if self.iteration is None else self.iteration,
            "file_iteration_index": self.file_iteration_index,
            "total_tokens": self.total_tokens,
            "agents": {
                agent.agent: agent.total_tokens
                for agent in self.agents
            },
        }


@dataclass(frozen=True)
class TokenUsageReport:
    summary_path: str
    total_tokens: int
    agents: tuple[AgentTokenUsage, ...]
    iterations: tuple[IterationTokenUsage, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_path": self.summary_path,
            "total_tokens": self.total_tokens,
            "agents": {
                agent.agent: agent.total_tokens
                for agent in self.agents
            },
            "iterations": [iteration.to_dict() for iteration in self.iterations],
        }


@dataclass(frozen=True)
class TruncationStats:
    analyzed_calls: int
    truncated_calls: int

    @property
    def truncated_response_percent(self) -> float | None:
        if self.analyzed_calls == 0:
            return None
        return round(self.truncated_calls / self.analyzed_calls * 100, 2)

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "analyzed_calls": self.analyzed_calls,
            "truncated_calls": self.truncated_calls,
            "truncated_response_percent": self.truncated_response_percent,
        }


@dataclass(frozen=True)
class AgentTruncationStats:
    agent: str
    stats: TruncationStats


@dataclass(frozen=True)
class IterationTruncationStats:
    iteration: int | None
    file_iteration_index: int | None
    stats: TruncationStats
    agents: tuple[AgentTruncationStats, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": "initial" if self.iteration is None else self.iteration,
            "file_iteration_index": self.file_iteration_index,
            **self.stats.to_dict(),
            "agents": {
                agent.agent: agent.stats.to_dict()
                for agent in self.agents
            },
        }


@dataclass(frozen=True)
class TruncationReport:
    events_path: str
    detection_methods: tuple[str, ...]
    stats: TruncationStats
    agents: tuple[AgentTruncationStats, ...]
    iterations: tuple[IterationTruncationStats, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "events_path": self.events_path,
            "detection_methods": list(self.detection_methods),
            **self.stats.to_dict(),
            "agents": {
                agent.agent: agent.stats.to_dict()
                for agent in self.agents
            },
            "iterations": [iteration.to_dict() for iteration in self.iterations],
        }


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
            "truncation_analyzed_calls": 0,
            "truncated_calls": 0,
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
        if isinstance(event.get("truncated"), bool):
            bucket["truncation_analyzed_calls"] += 1
            bucket["truncated_calls"] += int(event["truncated"])

    def _write_summary(self) -> None:
        temporary_path = self._summary_path.with_suffix(".json.tmp")
        with temporary_path.open("w", encoding="utf-8") as summary_file:
            json.dump(self._summary, summary_file, ensure_ascii=False, indent=2)
        os.replace(temporary_path, self._summary_path)


def load_token_usage_report(output_dir: str | Path) -> TokenUsageReport | None:
    """Load totals needed by offline evaluation from a run summary."""

    summary_path = Path(output_dir) / TokenUsageRecorder.SUMMARY_FILENAME
    if not summary_path.is_file():
        return None

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid token usage summary: {summary_path}") from error
    if not isinstance(summary, dict):
        raise ValueError(f"invalid token usage summary: {summary_path}")

    total_tokens = _read_total_tokens(summary.get("totals"), "totals")
    agents = _read_agent_usage(summary.get("agents"), "agents")
    iterations = _include_zero_usage_agents(
        _read_iteration_usage(summary.get("iterations")),
        agents,
    )
    return TokenUsageReport(
        summary_path=str(summary_path.resolve()),
        total_tokens=total_tokens,
        agents=agents,
        iterations=iterations,
    )


def _read_agent_usage(
    raw_agents: Any,
    field_name: str,
) -> tuple[AgentTokenUsage, ...]:
    if not isinstance(raw_agents, dict):
        raise ValueError(f"invalid token usage summary field: {field_name}")

    return tuple(
        AgentTokenUsage(
            agent=agent,
            total_tokens=_read_total_tokens(bucket, f"{field_name}.{agent}"),
        )
        for agent, bucket in sorted(raw_agents.items())
    )


def _read_iteration_usage(raw_iterations: Any) -> tuple[IterationTokenUsage, ...]:
    if not isinstance(raw_iterations, dict):
        raise ValueError("invalid token usage summary field: iterations")

    parsed_iterations = []
    for iteration_key, bucket in raw_iterations.items():
        if not isinstance(bucket, dict):
            raise ValueError(
                f"invalid token usage summary field: iterations.{iteration_key}"
            )

        if iteration_key == "initial":
            iteration = None
            file_iteration_index = None
        else:
            try:
                file_iteration_index = int(iteration_key)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"invalid token usage iteration: {iteration_key}"
                ) from error
            if file_iteration_index < 0:
                raise ValueError(
                    f"invalid token usage iteration: {iteration_key}"
                )
            iteration = file_iteration_index + 1

        parsed_iterations.append(
            IterationTokenUsage(
                iteration=iteration,
                file_iteration_index=file_iteration_index,
                total_tokens=_read_total_tokens(
                    bucket.get("totals"),
                    f"iterations.{iteration_key}.totals",
                ),
                agents=_read_agent_usage(
                    bucket.get("agents"),
                    f"iterations.{iteration_key}.agents",
                ),
            )
        )

    return tuple(
        sorted(
            parsed_iterations,
            key=lambda item: (
                item.file_iteration_index is not None,
                item.file_iteration_index or 0,
            ),
        )
    )


def _read_total_tokens(raw_bucket: Any, field_name: str) -> int:
    if not isinstance(raw_bucket, dict):
        raise ValueError(f"invalid token usage summary field: {field_name}")

    total_tokens = raw_bucket.get("total_tokens")
    if (
        isinstance(total_tokens, bool)
        or not isinstance(total_tokens, int)
        or total_tokens < 0
    ):
        raise ValueError(
            f"invalid token usage summary field: {field_name}.total_tokens"
        )
    return total_tokens


def _include_zero_usage_agents(
    iterations: tuple[IterationTokenUsage, ...],
    agents: tuple[AgentTokenUsage, ...],
) -> tuple[IterationTokenUsage, ...]:
    agent_names = tuple(agent.agent for agent in agents)
    completed_iterations = []
    for iteration in iterations:
        totals_by_agent = {
            agent.agent: agent.total_tokens
            for agent in iteration.agents
        }
        completed_iterations.append(
            IterationTokenUsage(
                iteration=iteration.iteration,
                file_iteration_index=iteration.file_iteration_index,
                total_tokens=iteration.total_tokens,
                agents=tuple(
                    AgentTokenUsage(
                        agent=agent_name,
                        total_tokens=totals_by_agent.get(agent_name, 0),
                    )
                    for agent_name in agent_names
                ),
            )
        )
    return tuple(completed_iterations)


_LEGACY_OUTPUT_LIMIT_BY_STAGE = {
    "specification_lifting": 512,
    "alignment_selection": 64,
    "alignment_rule": 256,
    "generated_tests": 1024,
    "test_analysis": 512,
    "test_design": 512,
    "test_generation": 1024,
    "test_review": 1024,
}

_LEGACY_OUTPUT_LIMIT_BY_AGENT = {
    "Coder Agent": 1024,
    "Product Manager": 512,
    "Architect": 512,
    "Project Manager": 512,
    "Engineer": 1024,
    "Tester Agent": 1024,
    "Lifter Agent": 512,
    "Test Analyst": 512,
    "Test Designer": 512,
    "Test Generator": 1024,
    "Test Reviewer / Validator": 1024,
}


def load_truncation_report(output_dir: str | Path) -> TruncationReport | None:
    """Aggregate response truncation by agent and generation iteration."""

    events_path = Path(output_dir) / TokenUsageRecorder.EVENTS_FILENAME
    if not events_path.is_file():
        return None

    totals = _new_truncation_bucket()
    agents: dict[str, dict[str, int]] = {}
    iterations: dict[int | None, dict[str, Any]] = {}
    detection_methods = set()

    with events_path.open("r", encoding="utf-8") as events_file:
        for line in events_file:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue

            detected = _detect_event_truncation(event)
            if detected is None:
                continue
            truncated, detection_method = detected

            agent = event.get("agent")
            if not isinstance(agent, str) or not agent:
                continue
            valid_iteration, iteration_index = _read_event_iteration(
                event.get("iteration")
            )
            if not valid_iteration:
                continue

            detection_methods.add(detection_method)
            _add_truncation_result(totals, truncated)
            _add_truncation_result(
                agents.setdefault(agent, _new_truncation_bucket()),
                truncated,
            )

            iteration_bucket = iterations.setdefault(
                iteration_index,
                {"totals": _new_truncation_bucket(), "agents": {}},
            )
            _add_truncation_result(iteration_bucket["totals"], truncated)
            _add_truncation_result(
                iteration_bucket["agents"].setdefault(
                    agent,
                    _new_truncation_bucket(),
                ),
                truncated,
            )

    agent_names = tuple(sorted(agents))
    return TruncationReport(
        events_path=str(events_path.resolve()),
        detection_methods=tuple(sorted(detection_methods)),
        stats=_to_truncation_stats(totals),
        agents=tuple(
            AgentTruncationStats(agent, _to_truncation_stats(agents[agent]))
            for agent in agent_names
        ),
        iterations=tuple(
            _build_iteration_truncation_stats(
                iteration_index,
                iterations[iteration_index],
                agent_names,
            )
            for iteration_index in sorted(
                iterations,
                key=lambda value: (value is not None, value or 0),
            )
        ),
    )


def _new_truncation_bucket() -> dict[str, int]:
    return {"analyzed_calls": 0, "truncated_calls": 0}


def _add_truncation_result(bucket: dict[str, int], truncated: bool) -> None:
    bucket["analyzed_calls"] += 1
    bucket["truncated_calls"] += int(truncated)


def _to_truncation_stats(bucket: dict[str, int]) -> TruncationStats:
    return TruncationStats(
        analyzed_calls=bucket["analyzed_calls"],
        truncated_calls=bucket["truncated_calls"],
    )


def _build_iteration_truncation_stats(
    iteration_index: int | None,
    bucket: dict[str, Any],
    agent_names: tuple[str, ...],
) -> IterationTruncationStats:
    return IterationTruncationStats(
        iteration=(None if iteration_index is None else iteration_index + 1),
        file_iteration_index=iteration_index,
        stats=_to_truncation_stats(bucket["totals"]),
        agents=tuple(
            AgentTruncationStats(
                agent,
                _to_truncation_stats(
                    bucket["agents"].get(agent, _new_truncation_bucket())
                ),
            )
            for agent in agent_names
        ),
    )


def _detect_event_truncation(
    event: dict[str, Any],
) -> tuple[bool, str] | None:
    truncated = event.get("truncated")
    if isinstance(truncated, bool):
        detection_method = event.get("truncation_detection")
        if not isinstance(detection_method, str) or not detection_method:
            detection_method = "recorded_truncation_flag"
        return truncated, detection_method

    if event.get("estimated", False):
        return None

    output_tokens = event.get("output_tokens")
    if isinstance(output_tokens, bool) or not isinstance(output_tokens, int):
        return None

    max_output_tokens = event.get("max_output_tokens")
    if (
        isinstance(max_output_tokens, int)
        and not isinstance(max_output_tokens, bool)
        and max_output_tokens > 0
    ):
        return output_tokens >= max_output_tokens, "output_limit_heuristic"

    legacy_limit = _legacy_output_limit(event)
    if legacy_limit is None:
        return None
    return output_tokens >= legacy_limit, "legacy_output_limit_heuristic"


def _legacy_output_limit(event: dict[str, Any]) -> int | None:
    stage = event.get("stage")
    if isinstance(stage, str) and stage in _LEGACY_OUTPUT_LIMIT_BY_STAGE:
        return _LEGACY_OUTPUT_LIMIT_BY_STAGE[stage]

    agent = event.get("agent")
    if isinstance(agent, str):
        return _LEGACY_OUTPUT_LIMIT_BY_AGENT.get(agent)
    return None


def _read_event_iteration(value: Any) -> tuple[bool, int | None]:
    if value is None:
        return True, None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return False, None
    return True, value
