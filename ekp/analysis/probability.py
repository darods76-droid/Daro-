"""Wahrscheinlichkeitsmodell.

Die gesammelte Nachrichten-Evidenz wird zu einer erwarteten Abweichung von
der Konsensprognose verdichtet (in Sigma-Einheiten). Um diesen Erwartungswert
liegt eine Normalverteilung; ein Toleranzband +/- tau definiert, wann die
Prognose als "bestaetigt" gilt.

        P(bestaetigt) = P(-tau < Z < +tau)   mit Z ~ N(mu, 1)
        P(hoeher)     = P(Z > +tau)
        P(niedriger)  = P(Z < -tau)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# Evidenzmasse, ab der die Nachrichtenlage als "halb belastbar" gilt.
MASS_HALF = 1.2


def phi(x: float) -> float:
    """Verteilungsfunktion der Standardnormalverteilung."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass(frozen=True)
class ProbabilityResult:
    p_above: float
    p_below: float
    p_confirm: float
    mu: float
    confidence: float
    evidence_mass: float
    agreement: float

    def as_triple(self) -> tuple[float, float, float]:
        return self.p_above, self.p_confirm, self.p_below


def aggregate(
    signed_values: list[float],
    *,
    evidence_scale: float = 3.0,
    confirm_band: float = 0.5,
    prior_mu: float = 0.0,
    source_count: int = 0,
    mu_max: float = 2.0,
) -> ProbabilityResult:
    """Verdichtet Einzelsignale zu Wahrscheinlichkeiten.

    ``signed_values`` sind die gerichteten, bereits gewichteten Evidenzwerte
    (positiv = spricht fuer einen Wert ueber der Prognose).
    """
    total = sum(signed_values)
    mass = sum(abs(v) for v in signed_values)
    agreement = abs(total) / mass if mass > 1e-9 else 0.0

    # tanh haelt die erwartete Abweichung in einem plausiblen Band: auch eine
    # Flut gleichgerichteter Meldungen kann die Prognose nicht beliebig kippen.
    mu = mu_max * math.tanh(total / max(evidence_scale, 1e-6)) + prior_mu

    tau = max(confirm_band, 1e-6)
    p_above = 1.0 - phi(tau - mu)
    p_below = phi(-tau - mu)
    p_confirm = max(0.0, 1.0 - p_above - p_below)

    # Normalisieren gegen Rundungsdrift.
    s = p_above + p_below + p_confirm
    if s > 0:
        p_above, p_below, p_confirm = p_above / s, p_below / s, p_confirm / s

    mass_score = 1.0 - 0.5 ** (mass / MASS_HALF)    # Evidenzmasse MASS_HALF => 0.5
    diversity = min(1.0, source_count / 4.0)
    confidence = mass_score * (0.55 + 0.25 * diversity + 0.20 * agreement)

    return ProbabilityResult(
        p_above=p_above,
        p_below=p_below,
        p_confirm=p_confirm,
        mu=mu,
        confidence=min(1.0, max(0.0, confidence)),
        evidence_mass=mass,
        agreement=agreement,
    )


def verdict_for(result: ProbabilityResult, min_confidence: float = 0.25) -> str:
    """Leitet aus den Wahrscheinlichkeiten das Urteil ab."""
    if result.evidence_mass <= 0 or result.confidence < min_confidence:
        return "UNBESTAETIGT"
    best = max(
        (result.p_confirm, "BESTAETIGT"),
        (result.p_above, "WIDERLEGT_HOEHER"),
        (result.p_below, "WIDERLEGT_NIEDRIGER"),
        key=lambda pair: pair[0],
    )
    return best[1]


def brier_score(p_above: float, p_confirm: float, p_below: float, outcome: str) -> float:
    """Mehrklassiger Brier-Score (0 = perfekt, 2 = maximal falsch)."""
    target = {"HOEHER": (1.0, 0.0, 0.0), "BESTAETIGT": (0.0, 1.0, 0.0), "NIEDRIGER": (0.0, 0.0, 1.0)}
    y = target.get(outcome)
    if y is None:
        raise ValueError(f"unbekanntes Ergebnis: {outcome}")
    p = (p_above, p_confirm, p_below)
    return sum((pi - yi) ** 2 for pi, yi in zip(p, y))
