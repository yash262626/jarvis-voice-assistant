"""Browser actions must build properly encoded URLs and never open anything else."""

from __future__ import annotations

import pytest

from actions.browser_actions import BrowserActions, register
from core.models import Action


@pytest.fixture
def opened():
    return []


@pytest.fixture
def browser(context, opened):
    return BrowserActions(context, opener=lambda url: (opened.append(url), True)[1])


def test_google_search_url(browser, opened):
    result = browser.web_search(Action("web_search", {"query": "tesla stock",
                                                      "engine": "google"}))
    assert result.success
    assert opened == ["https://www.google.com/search?q=tesla+stock"]


def test_youtube_search_url(browser, opened):
    browser.youtube_search(Action("youtube_search", {"query": "python tutorials"}))
    assert opened == ["https://www.youtube.com/results?search_query=python+tutorials"]


def test_query_is_percent_encoded(browser, opened):
    browser.web_search(Action("web_search", {"query": "cable 33 kV & armoured?"}))
    assert "&" not in opened[0].split("?q=")[1]
    assert "%26" in opened[0]


def test_unicode_query(browser, opened):
    browser.youtube_search(Action("youtube_search", {"query": "अरिजीत सिंह"}))
    assert opened[0].startswith("https://www.youtube.com/results?search_query=%")


def test_open_website(browser, opened):
    result = browser.open_website(Action("open_website", {"url": "https://github.com"}))
    assert result.success
    assert opened == ["https://github.com"]


def test_non_web_scheme_is_refused(browser, opened):
    result = browser.open_website(Action("open_website", {"url": "file:///C:/Windows"}))
    assert not result.success
    assert opened == []


def test_empty_query(browser, opened):
    assert not browser.web_search(Action("web_search", {"query": ""})).success
    assert opened == []


def test_register_adds_handlers(router, context):
    register(router, context)
    for intent in ("open_website", "web_search", "youtube_search"):
        assert router.has(intent)
