"""Reproducible metadata for one evaluation invocation."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_EVAL_DIR = Path(__file__).resolve().parent
_REPO_DIR = _EVAL_DIR.parents[1]
_RESULTS_DIR = _EVAL_DIR / "results"
_DEPENDENCIES = (
    "datasets",
    "elasticsearch",
    "httpx",
    "neo4j",
    "numpy",
    "redis",
    "sqlalchemy",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="milliseconds") if value else None


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_REPO_DIR,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def _git_metadata() -> dict[str, Any]:
    status = _git("status", "--porcelain=v1")
    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("branch", "--show-current"),
        "dirty": bool(status) if status is not None else None,
    }


def _fixture_fingerprints() -> dict[str, dict[str, Any]]:
    root = _EVAL_DIR / "fixtures"
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(_EVAL_DIR).as_posix()
        data = path.read_bytes()
        out[rel] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
    return out


def _working_tree_diff_sha256() -> str | None:
    try:
        result = subprocess.run(
            ["git", "diff", "--binary", "HEAD"],
            cwd=_REPO_DIR,
            check=True,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if not result.stdout:
        return None
    return hashlib.sha256(result.stdout).hexdigest()


def _dependency_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in _DEPENDENCIES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def describe_model(client) -> dict[str, str] | None:
    """Return non-secret client metadata suitable for reports."""
    if client is None:
        return None
    return {
        "model": client.model_name,
        "base_url": client.base_url,
    }


def stable_values_sha256(values: list[str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass
class RunManifest:
    request: dict[str, Any]
    run_id: str = field(default_factory=lambda: _now().strftime("%Y%m%d-%H%M%S-%f") + "-" + uuid.uuid4().hex[:6])
    status: str = "running"
    started_at: datetime = field(default_factory=_now)
    finished_at: datetime | None = None
    models: dict[str, Any] = field(default_factory=dict)
    datasets: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)
    error: dict[str, str] | None = None

    @property
    def path(self) -> Path:
        return _RESULTS_DIR / f"manifest-{self.run_id}.json"

    def record_artifact(
        self,
        *,
        kind: str,
        path: Path,
        benchmark: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        try:
            relative = path.resolve().relative_to(_EVAL_DIR).as_posix()
        except ValueError:
            relative = str(path.resolve())
        item: dict[str, Any] = {"kind": kind, "path": relative}
        if path.is_file():
            item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if benchmark:
            item["benchmark"] = benchmark
        if meta:
            item["meta"] = meta
        self.artifacts.append(item)
        self.write()

    def record_dataset(self, name: str, meta: dict[str, Any]) -> None:
        self.datasets[name] = meta
        self.write()

    def complete(self) -> None:
        self.status = "completed"
        self.finished_at = _now()
        self.write()

    def fail(self, exc: BaseException) -> None:
        self.status = "failed"
        self.finished_at = _now()
        self.error = {"type": type(exc).__name__, "message": str(exc)}
        self.write()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "status": self.status,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "duration_seconds": (
                round((self.finished_at - self.started_at).total_seconds(), 3)
                if self.finished_at else None
            ),
            "git": _git_metadata(),
            "working_tree_diff_sha256": _working_tree_diff_sha256(),
            "runtime": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "dependencies": _dependency_versions(),
            },
            "request": self.request,
            "models": self.models,
            "datasets": self.datasets,
            "fixture_fingerprints": _fixture_fingerprints(),
            "checks": self.checks,
            "artifacts": self.artifacts,
            "error": self.error,
        }

    def write(self) -> Path:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.path
