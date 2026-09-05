"""Pipeline: Kalender scannen, Nachrichten scannen, Prognosen bewerten, pruefen."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from .analysis import taxonomy
from .analysis.engine import AnalysisEngine
from .analysis.probability import brier_score
from .analysis.scoring import outcome_bucket, surprise_z
from .config import Settings, get_settings
from .models import Assessment, utcnow
from .providers import build_calendar_provider, build_news_provider
from .store import Store


@dataclass
class ScanReport:
    events_found: int = 0
    events_kept: int = 0
    news_found: int = 0
    news_pool: int = 0
    assessments: list[Assessment] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    calendar_provider: str = ""
    news_provider: str = ""

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for a in self.assessments:
            counts[a.verdict] = counts.get(a.verdict, 0) + 1
        return {
            "events_found": self.events_found,
            "events_kept": self.events_kept,
            "news_found": self.news_found,
            "news_pool": self.news_pool,
            "assessments": len(self.assessments),
            "verdicts": counts,
            "warnings": self.warnings,
            "calendar_provider": self.calendar_provider,
            "news_provider": self.news_provider,
        }


def scan(settings: Settings | None = None, store: Store | None = None) -> ScanReport:
    """Ein vollstaendiger Durchlauf: Kalender + Nachrichten -> Bewertungen."""
    settings = settings or get_settings()
    own_store = store is None
    store = store or Store(settings.db_path)
    report = ScanReport()

    try:
        # 1) Wirtschaftskalender scannen
        cal = build_calendar_provider(settings)
        report.calendar_provider = getattr(cal, "name", settings.calendar_provider)
        try:
            events = cal.fetch(settings.lookahead_hours)
        except Exception as exc:
            report.warnings.append(f"Kalender ({report.calendar_provider}) nicht erreichbar: {exc}")
            from .providers.demo import DemoCalendarProvider
            events = DemoCalendarProvider().fetch(settings.lookahead_hours)
            report.calendar_provider += " → Demo-Fallback"
        report.events_found = len(events)

        horizon = utcnow() + timedelta(hours=settings.lookahead_hours)
        kept = [e for e in events
                if e.importance >= settings.min_importance and e.when <= horizon]
        report.events_kept = len(kept)
        store.upsert_events(events)

        # 2) Nachrichten scannen
        news_src = build_news_provider(settings)
        report.news_provider = getattr(news_src, "name", settings.news_provider)
        try:
            news = news_src.fetch(settings.news_lookback_hours)
        except Exception as exc:
            report.warnings.append(f"Nachrichten ({report.news_provider}) nicht erreichbar: {exc}")
            news = []
        for err in getattr(news_src, "errors", []):
            report.warnings.append(f"Feed übersprungen: {err}")
        report.news_found = len(news)
        store.upsert_news(news)

        # 3) Nachrichtenpool aus dem Speicher (auch aus frueheren Laeufen)
        pool = store.news_since(utcnow() - timedelta(hours=settings.news_lookback_hours))
        report.news_pool = len(pool)
        if not pool:
            report.warnings.append(
                "Keine Nachrichten im Zeitfenster – ohne Nachrichtenlage bleibt jede "
                "Prognose unbestätigt. Prüfen Sie die Netzwerkverbindung oder setzen "
                "Sie EKP_NEWS_PROVIDER=demo.")

        # 4) Bewerten und speichern
        engine = AnalysisEngine(settings, priors=store.family_priors())
        report.assessments = engine.assess_all(kept, pool)
        for a in report.assessments:
            store.save_assessment(a)

        # 5) Bereits veroeffentlichte Termine gegenpruefen
        verify(settings, store)
        return report
    finally:
        if own_store:
            store.close()


def verify(settings: Settings | None = None, store: Store | None = None) -> list[dict[str, Any]]:
    """Vergleicht frueher abgegebene Urteile mit den tatsaechlichen Werten."""
    settings = settings or get_settings()
    own_store = store is None
    store = store or Store(settings.db_path)
    results: list[dict[str, Any]] = []
    try:
        for row, event in store.pending_verification():
            family = taxonomy.get_family(row["family"])
            z = surprise_z(event, family)
            if z is None:
                continue
            outcome = outcome_bucket(z, settings.confirm_band)
            verdict = row["verdict"]
            predicted = {"BESTAETIGT": "BESTAETIGT", "WIDERLEGT_HOEHER": "HOEHER",
                         "WIDERLEGT_NIEDRIGER": "NIEDRIGER"}.get(verdict)
            hit = None if predicted is None else int(predicted == outcome)
            record = {
                "event_id": event.event_id,
                "assessment_id": row["id"],
                "family": row["family"],
                "forecast": event.forecast,
                "actual": event.actual,
                "z": round(z, 4),
                "outcome": outcome,
                "verdict": verdict,
                "hit": hit,
                "brier": round(brier_score(row["p_above"], row["p_confirm"], row["p_below"], outcome), 4),
                "verified_at": utcnow().isoformat(),
            }
            store.save_verification(record)
            record["title"] = event.title
            results.append(record)
        return results
    finally:
        if own_store:
            store.close()
