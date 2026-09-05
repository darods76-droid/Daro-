"""Analyse-Engine: verbindet Kalendertermine mit der Nachrichtenlage."""

from __future__ import annotations

from ..config import Settings
from ..models import Assessment, EconomicEvent, NewsItem
from . import taxonomy
from .probability import aggregate, verdict_for
from .scoring import dedupe_evidence, score_news


class AnalysisEngine:
    """Bewertet Kalendertermine gegen einen Pool gescannter Nachrichten."""

    def __init__(self, settings: Settings, priors: dict[str, float] | None = None) -> None:
        self.settings = settings
        # Optionale, aus verifizierten Vergangenheitswerten gelernte Vorspannung
        # je Indikator-Familie (in Sigma). Wird gedaempft eingerechnet.
        self.priors = priors or {}

    def assess(self, event: EconomicEvent, news_pool: list[NewsItem]) -> Assessment:
        family = taxonomy.classify(event.title)
        notes: list[str] = []
        if family.note:
            notes.append(family.note)

        evidence = []
        for item in news_pool:
            ev = score_news(event, family, item, self.settings.news_half_life_hours)
            if ev is not None:
                evidence.append(ev)
        evidence = dedupe_evidence(evidence)

        prior = self.priors.get(family.key, 0.0)
        if prior:
            notes.append(
                f"Historische Vorspannung dieser Indikator-Familie: {prior:+.2f} σ "
                f"(aus verifizierten Terminen gelernt)."
            )

        result = aggregate(
            [e.signed for e in evidence],
            evidence_scale=self.settings.evidence_scale,
            confirm_band=self.settings.confirm_band,
            prior_mu=prior,
            source_count=len({e.source for e in evidence}),
        )
        verdict = verdict_for(result)

        if not event.has_forecast:
            notes.append("Für diesen Termin liegt keine Konsensprognose vor – "
                         "die Bewertung beschreibt die erwartete Richtung gegenüber dem Vorwert.")
        if not evidence:
            notes.append("Im Zeitfenster wurden keine thematisch passenden Nachrichten gefunden.")
        elif result.confidence < 0.25:
            notes.append("Die Nachrichtenlage ist zu dünn für ein belastbares Urteil.")

        return Assessment(
            event=event,
            family=family.key,
            p_above=result.p_above,
            p_below=result.p_below,
            p_confirm=result.p_confirm,
            expected_surprise=result.mu,
            confidence=result.confidence,
            verdict=verdict,
            evidence=sorted(evidence, key=lambda e: -e.strength),
            notes=notes,
        )

    def assess_all(self, events: list[EconomicEvent], news_pool: list[NewsItem]) -> list[Assessment]:
        return [self.assess(ev, news_pool) for ev in events]
