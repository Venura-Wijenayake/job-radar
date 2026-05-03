from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from scoring.text_utils import clean_html, normalize_unicode

from .base import BaseScraper

ALGOLIA_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
HN_FIREBASE = "https://hacker-news.firebaseio.com/v0/item/{}.json"
USER_AGENT = (
    "Mozilla/5.0 (compatible; job-radar/0.1; "
    "+https://github.com/) httpx"
)
DEFAULT_MAX_COMMENTS = 200
INTER_REQUEST_SLEEP = 0.05


class HackerNewsWhoIsHiringScraper(BaseScraper):
    """Two-step scraper for the latest "Ask HN: Who is hiring?" thread.

    1. Algolia search returns the most recent monthly thread by the
       author "whoishiring".
    2. Firebase API returns each top-level comment (a single job post)
       for that thread.

    Comments cap at ``max_comments`` (default 200) and we sleep 50ms
    between Firebase calls to be polite.
    """

    source_name = "HackerNewsWhoIsHiring"

    def __init__(
        self,
        client: httpx.Client | None = None,
        max_comments: int = DEFAULT_MAX_COMMENTS,
        sleep_between: float = INTER_REQUEST_SLEEP,
    ):
        self._client = client
        self._max_comments = max_comments
        self._sleep = sleep_between
        self._thread_id: int | None = None

    def _get_json(self, url: str, params: dict | None = None) -> Any:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self._client is not None:
            response = self._client.get(url, headers=headers, params=params, timeout=30)
        else:
            response = httpx.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def _find_latest_thread_id(self) -> int | None:
        params = {
            "query": "Ask HN: Who is hiring",
            "tags": "story,author_whoishiring",
            "hitsPerPage": 3,
        }
        data = self._get_json(ALGOLIA_SEARCH, params=params)
        if not isinstance(data, dict):
            return None
        hits = data.get("hits") or []
        if not hits:
            return None
        first = hits[0]
        if not isinstance(first, dict):
            return None
        try:
            return int(first.get("objectID"))
        except (TypeError, ValueError):
            return None

    def _fetch_comment(self, comment_id: int) -> dict | None:
        try:
            data = self._get_json(HN_FIREBASE.format(comment_id))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def fetch(self) -> list[dict[str, Any]]:
        thread_id = self._find_latest_thread_id()
        if thread_id is None:
            return []
        self._thread_id = thread_id

        thread = self._get_json(HN_FIREBASE.format(thread_id))
        if not isinstance(thread, dict):
            return []
        kids = thread.get("kids") or []
        kids = list(kids)[: self._max_comments]

        comments: list[dict[str, Any]] = []
        for cid in kids:
            comment = self._fetch_comment(cid)
            if comment is not None:
                comments.append(comment)
            if self._sleep > 0:
                time.sleep(self._sleep)
        return comments

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        if raw.get("deleted") or raw.get("dead"):
            return None
        text = raw.get("text")
        if not text:
            return None
        comment_id = raw.get("id")
        if comment_id is None:
            return None

        cleaned = normalize_unicode(clean_html(text))
        first_line = cleaned.split("\n", 1)[0].strip() if cleaned else ""
        title = first_line[:200] if first_line else f"HN Job #{comment_id}"

        company = "Unknown"
        if "|" in first_line:
            head = first_line.split("|", 1)[0].strip()
            if head:
                company = head

        posted_at: datetime | None = None
        ts = raw.get("time")
        if ts is not None:
            try:
                posted_at = datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(
                    tzinfo=None
                )
            except (TypeError, ValueError, OSError):
                posted_at = None

        return {
            "external_id": f"hn_{comment_id}",
            "title": title,
            "body": text,
            "url": f"https://news.ycombinator.com/item?id={comment_id}",
            "metadata_json": {
                "company": company,
                "author": raw.get("by"),
                "first_line": first_line,
                "thread_id": self._thread_id,
                "remote_type": "varied",
            },
            "posted_at": posted_at,
        }
