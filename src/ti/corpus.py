"""Corpus loading and evidence-preserving transcript chunking."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

from .governance import Redactor, canonical_hash


@dataclass
class EvidenceChunk:
    chunk_id: str
    meeting_id: str
    title: str
    date: str
    customer_domain: str
    call_type: str
    start_seconds: float
    end_seconds: float
    text: str
    source_hash: str


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def external_domains(emails: list[str]) -> list[str]:
    return sorted({email.rsplit("@", 1)[1].lower() for email in emails if "@" in email and not email.lower().endswith("@aegiscloud.com")})


def infer_call_type(title: str, emails: list[str]) -> str:
    domains = external_domains(emails)
    if not domains:
        return "Internal"
    support_hints = ("support case", "urgent:", "escalation:", "complete loss", "dashboard down", "failures", "issue", "bug")
    return "Support" if any(value in title.lower() for value in support_hints) else "External"


def chunk_meeting(folder: Path, sentences_per_chunk: int = 6) -> Iterator[EvidenceChunk]:
    info = read_json(folder / "meeting-info.json")
    transcript = read_json(folder / "transcript.json").get("data", [])
    domains = external_domains(info.get("allEmails", []))
    call_type = infer_call_type(info.get("title", ""), info.get("allEmails", []))
    redactor = Redactor()
    for offset in range(0, len(transcript), sentences_per_chunk):
        group = transcript[offset: offset + sentences_per_chunk]
        if not group:
            continue
        raw_text = " ".join(f"{row.get('speaker_name', 'Unknown')}: {row.get('sentence', '')}" for row in group)
        text, _ = redactor.redact(raw_text)
        chunk_id = f"{info['meetingId']}:{offset // sentences_per_chunk:03d}"
        yield EvidenceChunk(
            chunk_id=chunk_id,
            meeting_id=info["meetingId"],
            title=info.get("title", ""),
            date=info.get("startTime", "")[:10],
            customer_domain=";".join(domains),
            call_type=call_type,
            start_seconds=float(group[0].get("time", 0.0)),
            end_seconds=float(group[-1].get("endTime", group[-1].get("time", 0.0))),
            text=text,
            source_hash=canonical_hash(group),
        )


def load_corpus(data_dir: Path) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    for folder in sorted(data_dir.iterdir()):
        if folder.is_dir() and (folder / "meeting-info.json").exists():
            chunks.extend(chunk_meeting(folder))
    return chunks


def to_jsonable(chunks: list[EvidenceChunk]) -> list[dict[str, Any]]:
    return [asdict(chunk) for chunk in chunks]
