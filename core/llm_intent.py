"""Optional LLM fallback for sentences the rule engine cannot parse.

Disabled by default. When enabled it is still not allowed to *do* anything:
the model may only return JSON naming one of the allow-listed intents, which
is then validated exactly like a rule-engine action. There is deliberately no
path from model output to a shell command.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import List, Optional

from core.models import Action
from core.safety_manager import ALLOWED_INTENTS
from utils.config import Config
from utils.logger import get_logger

log = get_logger("core.llm")

SYSTEM_PROMPT = """You convert a Windows voice command into structured actions.

Reply with ONLY a JSON array, no prose, no markdown fences.
Each element: {"intent": "<intent>", ...parameters}

Allowed intents and parameters:
  open_application  {"application": "chrome"}
  close_application {"application": "notepad"}
  open_website      {"url": "https://example.com"}
  web_search        {"query": "...", "engine": "google"}
  youtube_search    {"query": "..."}
  type_text         {"text": "exact text to type at the cursor"}
  press_key         {"key": "enter", "times": 1}
  hotkey            {"keys": ["ctrl", "c"]}
  create_folder     {"name": "Projects", "location": "desktop"}
  open_folder       {"name": "downloads"}
  get_time          {}
  get_date          {}
  lock_pc           {}
  set_volume        {"direction": "up"}

Rules:
- "type/enter/write X" means type_text, never a web search.
- "search X" means web_search, never type_text.
- Preserve business identifiers exactly (RP0002442, 29AAFCJ4954L1ZY).
- If the command is unclear, return [].
"""


class LLMIntentEngine:
    """Thin, provider-agnostic JSON-only client. Fails closed on any error."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()

    # ------------------------------------------------------------------ API
    @property
    def enabled(self) -> bool:
        return bool(self.config.get("llm_enabled", False)) and bool(self._api_key())

    def parse(self, text: str) -> List[Action]:
        if not self.enabled or not text.strip():
            return []
        try:
            raw = self._request(text)
        except Exception as exc:                                # noqa: BLE001
            log.warning("LLM fallback unavailable: %s", exc)
            return []
        return self._to_actions(raw, text)

    # -------------------------------------------------------------- internals
    def _provider(self) -> str:
        return str(self.config.get("llm_provider", "anthropic")).lower()

    def _api_key(self) -> str:
        env = "ANTHROPIC_API_KEY" if self._provider() == "anthropic" else "OPENAI_API_KEY"
        return os.environ.get(env, "").strip()

    def _request(self, text: str) -> str:
        provider = self._provider()
        timeout = float(self.config.get("llm_timeout", 12))
        model = str(self.config.get("llm_model", "claude-sonnet-4-6"))

        if provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "content-type": "application/json",
                "x-api-key": self._api_key(),
                "anthropic-version": "2023-06-01",
            }
            payload = {
                "model": model,
                "max_tokens": 400,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": text}],
            }
        else:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self._api_key()}",
            }
            payload = {
                "model": model,
                "max_tokens": 400,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            }

        request = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))

        if provider == "anthropic":
            blocks = body.get("content", [])
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return body["choices"][0]["message"]["content"]

    def _to_actions(self, raw: str, original: str) -> List[Action]:
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            log.warning("LLM returned non-JSON output; ignoring")
            return []

        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            return []

        actions: List[Action] = []
        for item in parsed[:6]:
            if not isinstance(item, dict):
                continue
            intent = str(item.pop("intent", "")).strip()
            if intent not in ALLOWED_INTENTS or intent in {"unknown", "exit_app"}:
                log.warning("Discarded LLM intent %r (not allow-listed)", intent)
                continue
            actions.append(
                Action(intent=intent, params=item, raw_text=original,
                       confidence=0.6, source="llm")
            )
        return actions
