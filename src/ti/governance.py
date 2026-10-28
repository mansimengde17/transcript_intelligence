"""Governance primitives: PII controls, RBAC, lineage, and tamper-evident audit logs."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class AccessContext:
    subject: str
    role: str
    account_scopes: tuple[str, ...] = ()


class AuthorizationError(PermissionError):
    pass


class Authorizer:
    ROLE_ACTIONS = {
        "viewer": {"search", "read_redacted"},
        "analyst": {"search", "read_redacted", "analyze", "submit_feedback"},
        "admin": {"search", "read_redacted", "read_raw", "analyze", "submit_feedback", "manage"},
    }

    def require(self, context: AccessContext, action: str, account_domain: str = "") -> None:
        if action not in self.ROLE_ACTIONS.get(context.role, set()):
            raise AuthorizationError(f"Role {context.role!r} cannot perform {action!r}")
        if account_domain and context.account_scopes and account_domain not in context.account_scopes:
            raise AuthorizationError(f"Subject is not scoped to account {account_domain!r}")


class Redactor:
    PATTERNS = {
        "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        "phone": re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)"),
        "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "api_key": re.compile(r"\b(?:sk|rk|pk)_[A-Za-z0-9_-]{16,}\b"),
    }
    INJECTION_PATTERNS = tuple(
        re.compile(pattern, re.I)
        for pattern in (
            r"ignore (?:all|any|the) previous instructions",
            r"reveal (?:the )?(?:system|developer) prompt",
            r"act as (?:an? )?(?:admin|root)",
            r"exfiltrate|bypass (?:security|policy|authorization)",
        )
    )

    def redact(self, text: str) -> tuple[str, dict[str, int]]:
        counts: dict[str, int] = {}
        redacted = text
        for name, pattern in self.PATTERNS.items():
            redacted, count = pattern.subn(f"[REDACTED_{name.upper()}]", redacted)
            counts[name] = count
        return redacted, counts

    def prompt_injection_signals(self, text: str) -> list[str]:
        return [pattern.pattern for pattern in self.INJECTION_PATTERNS if pattern.search(text)]


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LineageRecord:
    artifact_id: str
    source_hashes: dict[str, str]
    transform: str
    transform_version: str
    output_hash: str
    created_at: str

    @classmethod
    def create(cls, artifact_id: str, sources: dict[str, Any], transform: str, version: str, output: Any) -> "LineageRecord":
        return cls(
            artifact_id=artifact_id,
            source_hashes={name: canonical_hash(value) for name, value in sources.items()},
            transform=transform,
            transform_version=version,
            output_hash=canonical_hash(output),
            created_at=datetime.now(timezone.utc).isoformat(),
        )


class AuditLedger:
    """Append-only JSONL log with a hash chain to expose tampering."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _last_hash(self) -> str:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return "GENESIS"
        with self.path.open("rb") as handle:
            lines = handle.read().splitlines()
        return json.loads(lines[-1])["entry_hash"]

    def append(self, event_type: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "actor": actor,
                "payload": payload,
                "previous_hash": self._last_hash(),
            }
            entry["entry_hash"] = canonical_hash(entry)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
            return entry

    def verify(self) -> tuple[bool, int]:
        previous = "GENESIS"
        count = 0
        if not self.path.exists():
            return True, 0
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                entry = json.loads(line)
                claimed = entry.pop("entry_hash")
                if entry["previous_hash"] != previous or canonical_hash(entry) != claimed:
                    return False, count
                previous = claimed
                count += 1
        return True, count
