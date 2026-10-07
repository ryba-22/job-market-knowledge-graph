from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from typing import Any


_WS = re.compile(r"\s+")


def norm_text(value: str | None) -> str:
    return _WS.sub(" ", (value or "").strip())


def norm_key(value: str | None) -> str:
    return norm_text(value).casefold()


@dataclass(frozen=True)
class PostingRef:
    source: str
    url: str
    source_posting_id: str


@dataclass
class ParsedPosting:
    source: str
    source_posting_id: str
    url: str
    title: str
    company_mention: str | None
    body_text: str
    source_specific: dict[str, Any] = field(default_factory=dict)

    def normalized_projection(self) -> dict[str, Any]:
        return {
            "title": norm_text(self.title),
            "company_mention": norm_text(self.company_mention),
            "body_text": norm_text(self.body_text),
        }

    def normalized_hash(self) -> str:
        payload = json.dumps(
            self.normalized_projection(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()
