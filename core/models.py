"""Dataclasses shared across the intent engine, router and action handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Action:
    """A single structured, validated instruction produced by the intent engine.

    The LLM (when enabled) and the rule engine both emit *only* this - never a
    shell string - which is what keeps the execution path safe.
    """

    intent: str
    params: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    confidence: float = 1.0
    source: str = "rules"          # rules | llm | gui | test

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {"intent": self.intent, **self.params}

    def __repr__(self) -> str:                                   # pragma: no cover
        return f"Action({self.intent}, {self.params})"


@dataclass
class ActionResult:
    """What happened when an action ran, plus what JARVIS should say about it."""

    success: bool = True
    speech: str = ""
    detail: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    needs_confirmation: bool = False
    pending: Optional["Action"] = None

    @classmethod
    def ok(cls, speech: str = "Done.", **data: Any) -> "ActionResult":
        return cls(success=True, speech=speech, data=data)

    @classmethod
    def fail(cls, speech: str, detail: str = "") -> "ActionResult":
        return cls(success=False, speech=speech, detail=detail or speech)

    @classmethod
    def confirm(cls, question: str, action: "Action") -> "ActionResult":
        return cls(success=True, speech=question, needs_confirmation=True, pending=action)


@dataclass
class Utterance:
    """One recognised phrase and how confident the recogniser was."""

    text: str = ""
    confidence: float = 0.0
    engine: str = ""
    duration: float = 0.0

    def __bool__(self) -> bool:
        return bool(self.text.strip())
