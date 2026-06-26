"""Dataclasses for browse drone snapshots and candidates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BrowseCandidate:
    """A single interactive element found on the page."""

    id: str  # stable per-snapshot id, e.g. "c0", "c1"
    role: str  # "link", "button", "textbox", "combobox", ...
    tag: str  # "a", "button", "input", "textarea", "select"
    label: str  # visible text, aria-label, placeholder, or name
    enabled: bool
    visible: bool
    href: str = ""  # only for links
    input_type: str = ""  # for inputs: "text", "email", "search", etc.

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "tag": self.tag,
            "label": self.label,
            "enabled": self.enabled,
            "visible": self.visible,
            "href": self.href,
            "input_type": self.input_type,
        }


@dataclass
class BrowseSnapshot:
    """Snapshot of a page state during a browse drone run."""

    url: str
    title: str
    body_excerpt: str  # first 2000 chars of body inner_text, normalized
    candidates: list[dict]  # list of candidate.to_dict()
    candidate_count: int

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "body_excerpt": self.body_excerpt,
            "candidates": self.candidates,
            "candidate_count": self.candidate_count,
        }
