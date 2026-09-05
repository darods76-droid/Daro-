"""Nachrichten-Scanner ueber oeffentliche RSS/Atom-Feeds (ohne API-Schluessel)."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from ..config import Settings
from ..models import NewsItem, utcnow
from .http import FetchError, get

# (URL, Quellenname, Gewicht) - Gewicht steht fuer die Verlaesslichkeit der Quelle.
DEFAULT_FEEDS: tuple[tuple[str, str, float], ...] = (
    ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "WSJ Markets", 0.95),
    ("https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml", "WSJ Business", 0.95),
    ("https://www.ft.com/rss/home", "Financial Times", 0.90),
    ("https://www.marketwatch.com/rss/topstories", "MarketWatch", 0.80),
    ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance", 0.70),
    ("https://www.investing.com/rss/news_25.rss", "Investing.com Indikatoren", 0.75),
    ("https://www.investing.com/rss/news_14.rss", "Investing.com Wirtschaft", 0.75),
    ("https://www.tagesschau.de/wirtschaft/index~rss2.xml", "tagesschau Wirtschaft", 0.90),
    ("https://www.handelsblatt.com/contentexport/feed/wirtschaft", "Handelsblatt", 0.90),
    ("https://www.faz.net/rss/aktuell/wirtschaft/", "FAZ Wirtschaft", 0.85),
    ("https://www.wiwo.de/contentexport/feed/rss/schlagzeilen", "WirtschaftsWoche", 0.80),
    ("https://www.spiegel.de/wirtschaft/index.rss", "Spiegel Wirtschaft", 0.80),
    ("https://rss.sueddeutsche.de/rss/Wirtschaft", "SZ Wirtschaft", 0.80),
    ("https://www.ecb.europa.eu/rss/press.html", "EZB Presse", 1.00),
    ("https://www.federalreserve.gov/feeds/press_all.xml", "Fed Presse", 1.00),
)

_TAG_RE = re.compile(r"<[^>]+>")
_NS_RE = re.compile(r"^\{[^}]+\}")


def _localname(tag: str) -> str:
    return _NS_RE.sub("", tag)


def _find_text(node: ET.Element, *names: str) -> str:
    """Erstes passendes Kindelement, unabhaengig vom XML-Namespace."""
    wanted = set(names)
    for child in node:
        if _localname(child.tag) in wanted:
            if child.text and child.text.strip():
                return child.text.strip()
            # Atom: <link href="..."/>
            href = child.attrib.get("href")
            if href:
                return href.strip()
    return ""


def parse_datetime(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)              # RFC 822 (RSS)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))   # ISO 8601 (Atom)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_feed(xml_text: str, source: str, weight: float) -> list[NewsItem]:
    """Liest RSS-2.0- und Atom-Feeds."""
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        return []

    items: list[NewsItem] = []
    for node in root.iter():
        if _localname(node.tag) not in ("item", "entry"):
            continue
        title = _TAG_RE.sub(" ", _find_text(node, "title")).strip()
        if not title:
            continue
        link = _find_text(node, "link", "id", "guid")
        summary = _TAG_RE.sub(" ", _find_text(node, "description", "summary", "content")).strip()
        published = parse_datetime(_find_text(node, "pubDate", "published", "updated", "date"))
        if published is None:
            published = utcnow()
        items.append(NewsItem(
            title=title,
            summary=summary[:600],
            url=link,
            published=published,
            source=source,
            source_weight=weight,
        ))
    return items


class RSSNewsProvider:
    """Scannt eine Liste von Feeds und liefert die Meldungen im Zeitfenster."""

    name = "rss"

    def __init__(self, settings: Settings, feeds=None) -> None:
        self.settings = settings
        self.feeds = feeds or self._feeds_from_env()
        self.errors: list[str] = []

    @staticmethod
    def _feeds_from_env() -> tuple[tuple[str, str, float], ...]:
        raw = os.environ.get("EKP_RSS_FEEDS", "").strip()
        if not raw:
            return DEFAULT_FEEDS
        feeds = []
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = [p.strip() for p in entry.split("|")]
            url = parts[0]
            source = parts[1] if len(parts) > 1 else url.split("/")[2]
            weight = float(parts[2]) if len(parts) > 2 else 0.7
            feeds.append((url, source, weight))
        return tuple(feeds)

    def fetch(self, lookback_hours: int) -> list[NewsItem]:
        cutoff = utcnow() - timedelta(hours=lookback_hours)
        seen: set[str] = set()
        out: list[NewsItem] = []
        self.errors = []

        for url, source, weight in self.feeds:
            try:
                xml_text = get(url, timeout=self.settings.http_timeout)
            except FetchError as exc:
                self.errors.append(str(exc))
                continue
            for item in parse_feed(xml_text, source, weight):
                if item.published < cutoff:
                    continue
                key = item.news_id
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)

        return sorted(out, key=lambda n: -n.published.timestamp())
