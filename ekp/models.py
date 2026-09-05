"""Datenmodelle der App (reine Standardbibliothek)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


@dataclass
class EconomicEvent:
    """Ein Termin aus dem Wirtschaftskalender."""

    title: str
    country: str
    when: datetime
    importance: int = 2              # 1 = niedrig, 2 = mittel, 3 = hoch
    currency: str = ""
    forecast: float | None = None    # Konsensprognose
    previous: float | None = None
    actual: float | None = None      # erst nach Veroeffentlichung gesetzt
    unit: str = ""
    source: str = "demo"
    event_id: str = ""

    def __post_init__(self) -> None:
        if self.when.tzinfo is None:
            self.when = self.when.replace(tzinfo=timezone.utc)
        if not self.event_id:
            self.event_id = self.make_id(self.country, self.title, self.when)

    @staticmethod
    def make_id(country: str, title: str, when: datetime) -> str:
        raw = f"{country.upper()}|{title.strip().lower()}|{when.astimezone(timezone.utc):%Y-%m-%dT%H:%M}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def has_forecast(self) -> bool:
        return self.forecast is not None

    @property
    def is_released(self) -> bool:
        return self.actual is not None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["when"] = _iso(self.when)
        return d


@dataclass
class NewsItem:
    """Eine gescannte Nachricht."""

    title: str
    url: str
    published: datetime
    source: str
    summary: str = ""
    source_weight: float = 0.6
    news_id: str = ""

    def __post_init__(self) -> None:
        if self.published.tzinfo is None:
            self.published = self.published.replace(tzinfo=timezone.utc)
        if not self.news_id:
            self.news_id = hashlib.sha1((self.url or self.title).encode("utf-8")).hexdigest()[:16]

    @property
    def text(self) -> str:
        return f"{self.title}. {self.summary}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["published"] = _iso(self.published)
        return d


@dataclass
class Evidence:
    """Ein aus einer Nachricht abgeleitetes Signal fuer genau einen Termin."""

    news_id: str
    headline: str
    url: str
    source: str
    published: datetime
    direction: int          # +1 = spricht fuer Wert ueber Prognose, -1 = darunter
    strength: float         # >= 0, bereits gewichtet (Quelle, Aktualitaet, Relevanz)
    relevance: float
    recency: float
    signals: list[str] = field(default_factory=list)   # erkannte Themen/Begriffe
    rationale: str = ""

    @property
    def signed(self) -> float:
        return self.direction * self.strength

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["published"] = _iso(self.published)
        d["signed"] = round(self.signed, 4)
        return d


@dataclass
class Assessment:
    """Bewertung eines Kalendertermins auf Basis der Nachrichtenlage."""

    event: EconomicEvent
    family: str                  # erkannte Indikator-Familie
    p_above: float               # Wahrscheinlichkeit: Ist-Wert deutlich ueber Prognose
    p_below: float               # Wahrscheinlichkeit: Ist-Wert deutlich unter Prognose
    p_confirm: float             # Wahrscheinlichkeit: Prognose wird bestaetigt (Toleranzband)
    expected_surprise: float     # erwartete Abweichung in Sigma-Einheiten
    confidence: float            # 0..1, Belastbarkeit der Nachrichtenlage
    verdict: str                 # BESTAETIGT | WIDERLEGT_HOEHER | WIDERLEGT_NIEDRIGER | UNBESTAETIGT
    evidence: list[Evidence] = field(default_factory=list)
    generated_at: datetime = field(default_factory=utcnow)
    notes: list[str] = field(default_factory=list)

    VERDICT_LABELS = {
        "BESTAETIGT": "Prognose bestätigt",
        "WIDERLEGT_HOEHER": "Prognose widerlegt – höher erwartet",
        "WIDERLEGT_NIEDRIGER": "Prognose widerlegt – niedriger erwartet",
        "UNBESTAETIGT": "Nachrichtenlage zu dünn",
    }

    @property
    def verdict_label(self) -> str:
        return self.VERDICT_LABELS.get(self.verdict, self.verdict)

    @property
    def headline_probability(self) -> float:
        """Der Wahrscheinlichkeitswert, der zum Urteil gehoert."""
        if self.verdict == "WIDERLEGT_HOEHER":
            return self.p_above
        if self.verdict == "WIDERLEGT_NIEDRIGER":
            return self.p_below
        return self.p_confirm

    def to_dict(self, with_evidence: bool = True) -> dict[str, Any]:
        d = {
            "event": self.event.to_dict(),
            "family": self.family,
            "p_above": round(self.p_above, 4),
            "p_below": round(self.p_below, 4),
            "p_confirm": round(self.p_confirm, 4),
            "expected_surprise": round(self.expected_surprise, 4),
            "confidence": round(self.confidence, 4),
            "verdict": self.verdict,
            "verdict_label": self.verdict_label,
            "headline_probability": round(self.headline_probability, 4),
            "generated_at": _iso(self.generated_at),
            "notes": list(self.notes),
            "evidence_count": len(self.evidence),
        }
        if with_evidence:
            d["evidence"] = [e.to_dict() for e in self.evidence]
        return d
