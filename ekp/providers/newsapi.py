"""Nachrichten ueber NewsAPI.org (optional, benoetigt EKP_NEWSAPI_KEY)."""

from __future__ import annotations

import urllib.parse
from datetime import timedelta

from ..config import Settings
from ..models import NewsItem, utcnow
from .http import FetchError, get_json
from .rss import parse_datetime

QUERY = ("inflation OR arbeitsmarkt OR konjunktur OR notenbank OR economy OR "
         "inflation OR jobs OR \"central bank\"")


class NewsAPIProvider:
    name = "newsapi"

    def __init__(self, settings: Settings) -> None:
        if not settings.newsapi_key:
            raise ValueError("EKP_NEWSAPI_KEY ist nicht gesetzt.")
        self.settings = settings

    def fetch(self, lookback_hours: int) -> list[NewsItem]:
        since = (utcnow() - timedelta(hours=lookback_hours)).strftime("%Y-%m-%dT%H:%M:%S")
        params = urllib.parse.urlencode({
            "q": QUERY, "from": since, "language": "de", "sortBy": "publishedAt",
            "pageSize": "100",
        })
        url = f"https://newsapi.org/v2/everything?{params}"
        payload = get_json(url, timeout=self.settings.http_timeout,
                           headers={"X-Api-Key": self.settings.newsapi_key})
        if payload.get("status") != "ok":
            raise FetchError(f"NewsAPI-Fehler: {payload.get('message')}")

        items = []
        for art in payload.get("articles", []):
            published = parse_datetime(art.get("publishedAt", "")) or utcnow()
            source = (art.get("source") or {}).get("name") or "NewsAPI"
            items.append(NewsItem(
                title=art.get("title") or "",
                summary=(art.get("description") or "")[:600],
                url=art.get("url") or "",
                published=published,
                source=source,
                source_weight=0.75,
            ))
        return [i for i in items if i.title]
