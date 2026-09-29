"""Browser control: open sites, Google search, YouTube search.

All queries are percent-encoded with urllib, never string-concatenated, so a
dictated query containing &, ? or # cannot alter the URL structure.
"""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from typing import Any, Optional
from urllib.parse import urlparse

from core.models import Action, ActionResult
from utils.helpers import build_search_url, build_youtube_search_url, find_executable
from utils.logger import get_logger

log = get_logger("actions.browser")

_ALLOWED_SCHEMES = {"http", "https"}


class BrowserActions:
    """Handlers for ``open_website``, ``web_search`` and ``youtube_search``."""

    def __init__(self, context: Any, opener: Optional[Any] = None) -> None:
        self.context = context
        self.config = context.config
        self._opener = opener                    # injected in unit tests

    # ------------------------------------------------------------------ core
    def _open(self, url: str) -> bool:
        """Launch a URL in the configured browser. Returns True on success."""
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            log.warning("Refusing to open non-web URL: %s", url)
            return False

        if self._opener is not None:
            return bool(self._opener(url))

        preferred = str(self.config.get("browser", "default")).lower()
        if preferred and preferred != "default":
            executable = find_executable([f"{preferred}.exe", preferred], preferred)
            if executable:
                try:
                    subprocess.Popen([executable, url], close_fds=True)
                    return True
                except OSError as exc:
                    log.warning("Could not start %s (%s); using default browser",
                                preferred, exc)
        try:
            return bool(webbrowser.open(url, new=2, autoraise=True))
        except Exception as exc:                                # noqa: BLE001
            log.error("Failed to open browser: %s", exc)
            return False

    # -------------------------------------------------------------- handlers
    def open_website(self, action: Action) -> ActionResult:
        url = str(action.get("url", "")).strip()
        if not url:
            return ActionResult.fail("I didn't catch which site.")
        name = action.get("name") or urlparse(url).netloc.replace("www.", "")
        if not self._open(url):
            return ActionResult.fail(f"I couldn't open {name}.")
        return ActionResult(success=True, speech=f"Opening {name}.", detail=url,
                            data={"url": url})

    def web_search(self, action: Action) -> ActionResult:
        query = str(action.get("query", "")).strip()
        if not query:
            return ActionResult.fail("What should I search for?")
        engine = str(action.get("engine")
                     or self.config.get("default_search_engine", "google")).lower()
        url = build_search_url(query, engine)
        if not self._open(url):
            return ActionResult.fail("I couldn't open the browser.")
        return ActionResult(success=True, speech=f"Searching {engine} for {query}.",
                            detail=url, data={"url": url, "query": query})

    def youtube_search(self, action: Action) -> ActionResult:
        query = str(action.get("query", "")).strip()
        if not query:
            return ActionResult.fail("What should I search on YouTube?")
        url = build_youtube_search_url(query)
        if not self._open(url):
            return ActionResult.fail("I couldn't open the browser.")
        return ActionResult(success=True, speech=f"Searching YouTube for {query}.",
                            detail=url, data={"url": url, "query": query})


def register(router: Any, context: Any) -> None:
    actions = BrowserActions(context)
    context.memory["browser_actions"] = actions
    router.register("open_website", actions.open_website, "Open a website")
    router.register("web_search", actions.web_search, "Search the web")
    router.register("youtube_search", actions.youtube_search, "Search YouTube")
