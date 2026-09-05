"""SQLite-Speicher: Termine, Nachrichten, Bewertungen und deren Ueberpruefung."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import Assessment, EconomicEvent, Evidence, NewsItem, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id   TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    country    TEXT,
    currency   TEXT,
    when_utc   TEXT NOT NULL,
    importance INTEGER,
    forecast   REAL,
    previous   REAL,
    actual     REAL,
    unit       TEXT,
    source     TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_when ON events(when_utc);

CREATE TABLE IF NOT EXISTS news (
    news_id       TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    url           TEXT,
    published_utc TEXT NOT NULL,
    source        TEXT,
    summary       TEXT,
    source_weight REAL,
    fetched_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news(published_utc);

CREATE TABLE IF NOT EXISTS assessments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id       TEXT NOT NULL,
    generated_at   TEXT NOT NULL,
    family         TEXT,
    p_above        REAL, p_confirm REAL, p_below REAL,
    mu             REAL, confidence REAL,
    verdict        TEXT,
    evidence_count INTEGER,
    notes          TEXT,
    FOREIGN KEY (event_id) REFERENCES events(event_id)
);
CREATE INDEX IF NOT EXISTS idx_assessments_event ON assessments(event_id, id DESC);

CREATE TABLE IF NOT EXISTS evidence (
    assessment_id INTEGER NOT NULL,
    news_id       TEXT,
    headline      TEXT,
    url           TEXT,
    source        TEXT,
    published_utc TEXT,
    direction     INTEGER,
    strength      REAL,
    relevance     REAL,
    recency       REAL,
    signals       TEXT,
    rationale     TEXT,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_assessment ON evidence(assessment_id);

CREATE TABLE IF NOT EXISTS verifications (
    event_id      TEXT PRIMARY KEY,
    assessment_id INTEGER,
    family        TEXT,
    forecast      REAL,
    actual        REAL,
    z             REAL,
    outcome       TEXT,
    verdict       TEXT,
    hit           INTEGER,
    brier         REAL,
    verified_at   TEXT NOT NULL
);
"""


def _dt(value: str | None) -> datetime:
    if not value:
        return utcnow()
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return utcnow()
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── Schreiben ────────────────────────────────────────────────────────────
    def upsert_events(self, events: Iterable[EconomicEvent]) -> int:
        now = utcnow().isoformat()
        rows = [(e.event_id, e.title, e.country, e.currency, e.when.isoformat(),
                 e.importance, e.forecast, e.previous, e.actual, e.unit, e.source, now)
                for e in events]
        self.conn.executemany(
            """INSERT INTO events (event_id,title,country,currency,when_utc,importance,
                                   forecast,previous,actual,unit,source,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(event_id) DO UPDATE SET
                   forecast=COALESCE(excluded.forecast, events.forecast),
                   previous=COALESCE(excluded.previous, events.previous),
                   actual=COALESCE(excluded.actual, events.actual),
                   importance=excluded.importance,
                   unit=excluded.unit,
                   updated_at=excluded.updated_at""", rows)
        self.conn.commit()
        return len(rows)

    def upsert_news(self, items: Iterable[NewsItem]) -> int:
        now = utcnow().isoformat()
        rows = [(n.news_id, n.title, n.url, n.published.isoformat(), n.source,
                 n.summary, n.source_weight, now) for n in items]
        self.conn.executemany(
            """INSERT INTO news (news_id,title,url,published_utc,source,summary,
                                 source_weight,fetched_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(news_id) DO NOTHING""", rows)
        self.conn.commit()
        return len(rows)

    def save_assessment(self, a: Assessment) -> int:
        cur = self.conn.execute(
            """INSERT INTO assessments (event_id,generated_at,family,p_above,p_confirm,p_below,
                                        mu,confidence,verdict,evidence_count,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (a.event.event_id, a.generated_at.isoformat(), a.family, a.p_above, a.p_confirm,
             a.p_below, a.expected_surprise, a.confidence, a.verdict, len(a.evidence),
             json.dumps(a.notes, ensure_ascii=False)))
        assessment_id = int(cur.lastrowid)
        self.conn.executemany(
            """INSERT INTO evidence (assessment_id,news_id,headline,url,source,published_utc,
                                     direction,strength,relevance,recency,signals,rationale)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(assessment_id, e.news_id, e.headline, e.url, e.source, e.published.isoformat(),
              e.direction, e.strength, e.relevance, e.recency,
              json.dumps(e.signals, ensure_ascii=False), e.rationale) for e in a.evidence])
        self.conn.commit()
        return assessment_id

    def set_actual(self, event_id: str, actual: float) -> None:
        self.conn.execute("UPDATE events SET actual=?, updated_at=? WHERE event_id=?",
                          (actual, utcnow().isoformat(), event_id))
        self.conn.commit()

    def save_verification(self, row: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO verifications (event_id,assessment_id,family,forecast,actual,z,
                                          outcome,verdict,hit,brier,verified_at)
               VALUES (:event_id,:assessment_id,:family,:forecast,:actual,:z,:outcome,
                       :verdict,:hit,:brier,:verified_at)
               ON CONFLICT(event_id) DO UPDATE SET
                   assessment_id=excluded.assessment_id, actual=excluded.actual,
                   z=excluded.z, outcome=excluded.outcome, verdict=excluded.verdict,
                   hit=excluded.hit, brier=excluded.brier, verified_at=excluded.verified_at""",
            row)
        self.conn.commit()

    # ── Lesen ────────────────────────────────────────────────────────────────
    def event(self, event_id: str) -> EconomicEvent | None:
        row = self.conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        return self._event_from_row(row) if row else None

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> EconomicEvent:
        return EconomicEvent(
            title=row["title"], country=row["country"] or "", currency=row["currency"] or "",
            when=_dt(row["when_utc"]), importance=row["importance"] or 2,
            forecast=row["forecast"], previous=row["previous"], actual=row["actual"],
            unit=row["unit"] or "", source=row["source"] or "", event_id=row["event_id"])

    def news_since(self, since: datetime) -> list[NewsItem]:
        rows = self.conn.execute("SELECT * FROM news WHERE published_utc >= ? ORDER BY published_utc DESC",
                                 (since.isoformat(),)).fetchall()
        return [NewsItem(title=r["title"], url=r["url"] or "", published=_dt(r["published_utc"]),
                         source=r["source"] or "", summary=r["summary"] or "",
                         source_weight=r["source_weight"] or 0.6, news_id=r["news_id"])
                for r in rows]

    def latest_assessments(self, upcoming_only: bool = True, limit: int = 200) -> list[dict[str, Any]]:
        """Je Termin die aktuellste Bewertung, inklusive Evidenz."""
        sql = """
            SELECT a.*, e.title, e.country, e.currency, e.when_utc, e.importance,
                   e.forecast, e.previous, e.actual, e.unit, e.source AS event_source,
                   v.outcome, v.hit, v.z, v.brier
            FROM assessments a
            JOIN events e ON e.event_id = a.event_id
            LEFT JOIN verifications v ON v.event_id = a.event_id
            WHERE a.id = (SELECT MAX(id) FROM assessments a2 WHERE a2.event_id = a.event_id)
        """
        params: list[Any] = []
        if upcoming_only:
            sql += " AND e.when_utc >= ?"
            params.append(utcnow().isoformat())
        sql += " ORDER BY e.when_utc ASC LIMIT ?"
        params.append(limit)

        out = []
        for row in self.conn.execute(sql, params).fetchall():
            out.append(self._assessment_dict(row))
        return out

    def _assessment_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        ev_rows = self.conn.execute(
            "SELECT * FROM evidence WHERE assessment_id=? ORDER BY strength DESC", (row["id"],)
        ).fetchall()
        verdict = row["verdict"]
        headline_p = {"WIDERLEGT_HOEHER": row["p_above"],
                      "WIDERLEGT_NIEDRIGER": row["p_below"]}.get(verdict, row["p_confirm"])
        return {
            "assessment_id": row["id"],
            "event": {
                "event_id": row["event_id"], "title": row["title"], "country": row["country"],
                "currency": row["currency"], "when": row["when_utc"],
                "importance": row["importance"], "forecast": row["forecast"],
                "previous": row["previous"], "actual": row["actual"], "unit": row["unit"],
                "source": row["event_source"],
            },
            "family": row["family"],
            "p_above": row["p_above"], "p_confirm": row["p_confirm"], "p_below": row["p_below"],
            "expected_surprise": row["mu"], "confidence": row["confidence"],
            "verdict": verdict,
            "verdict_label": Assessment.VERDICT_LABELS.get(verdict, verdict),
            "headline_probability": headline_p,
            "generated_at": row["generated_at"],
            "notes": json.loads(row["notes"] or "[]"),
            "evidence_count": row["evidence_count"],
            "verification": ({"outcome": row["outcome"], "hit": row["hit"],
                              "z": row["z"], "brier": row["brier"]}
                             if row["outcome"] is not None else None),
            "evidence": [{
                "news_id": e["news_id"], "headline": e["headline"], "url": e["url"],
                "source": e["source"], "published": e["published_utc"],
                "direction": e["direction"], "strength": e["strength"],
                "relevance": e["relevance"], "recency": e["recency"],
                "signed": round((e["direction"] or 0) * (e["strength"] or 0), 4),
                "signals": json.loads(e["signals"] or "[]"), "rationale": e["rationale"],
            } for e in ev_rows],
        }

    def pending_verification(self) -> list[tuple[sqlite3.Row, EconomicEvent]]:
        """Vergangene Termine mit Ist-Wert, fuer die noch keine Pruefung vorliegt."""
        rows = self.conn.execute("""
            SELECT a.*, e.title, e.country, e.currency, e.when_utc, e.importance,
                   e.forecast, e.previous, e.actual, e.unit, e.source AS event_source
            FROM assessments a
            JOIN events e ON e.event_id = a.event_id
            LEFT JOIN verifications v ON v.event_id = a.event_id
            WHERE a.id = (SELECT MAX(id) FROM assessments a2 WHERE a2.event_id = a.event_id)
              AND e.actual IS NOT NULL AND e.forecast IS NOT NULL AND v.event_id IS NULL
        """).fetchall()
        return [(r, EconomicEvent(
            title=r["title"], country=r["country"] or "", currency=r["currency"] or "",
            when=_dt(r["when_utc"]), importance=r["importance"] or 2, forecast=r["forecast"],
            previous=r["previous"], actual=r["actual"], unit=r["unit"] or "",
            source=r["event_source"] or "", event_id=r["event_id"])) for r in rows]

    # ── Auswertung ───────────────────────────────────────────────────────────
    def scoreboard(self) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT COUNT(*) n, COUNT(hit) n_scored, AVG(hit) hitrate, AVG(brier) brier "
            "FROM verifications").fetchone()
        by_family = self.conn.execute("""
            SELECT family, COUNT(*) n, COUNT(hit) n_scored, AVG(hit) hitrate,
                   AVG(brier) brier, AVG(z) mean_z
            FROM verifications GROUP BY family ORDER BY n DESC""").fetchall()
        by_verdict = self.conn.execute("""
            SELECT verdict, COUNT(*) n, AVG(hit) hitrate
            FROM verifications GROUP BY verdict ORDER BY n DESC""").fetchall()
        return {
            "n": row["n"] or 0,
            "n_scored": row["n_scored"] or 0,
            "hit_rate": round(row["hitrate"], 4) if row["hitrate"] is not None else None,
            "brier": round(row["brier"], 4) if row["brier"] is not None else None,
            "by_family": [dict(r) for r in by_family],
            "by_verdict": [dict(r) for r in by_verdict],
        }

    def family_priors(self, shrink: float = 10.0, cap: float = 1.0) -> dict[str, float]:
        """Aus verifizierten Terminen gelernte Vorspannung je Familie (in Sigma).

        Bei wenigen Beobachtungen wird stark zur Null hin geschrumpft, damit ein
        Zufallstreffer das Modell nicht verbiegt.
        """
        priors: dict[str, float] = {}
        for r in self.conn.execute(
                "SELECT family, COUNT(*) n, AVG(z) mean_z FROM verifications GROUP BY family"):
            n, mean_z, family = r["n"] or 0, r["mean_z"], r["family"]
            if not family or not n or mean_z is None:
                continue
            value = mean_z * (n / (n + shrink))
            priors[family] = round(max(-cap, min(cap, value)), 4)
        return priors

    def counts(self) -> dict[str, int]:
        def one(sql: str) -> int:
            return int(self.conn.execute(sql).fetchone()[0])
        return {
            "events": one("SELECT COUNT(*) FROM events"),
            "news": one("SELECT COUNT(*) FROM news"),
            "assessments": one("SELECT COUNT(*) FROM assessments"),
            "verifications": one("SELECT COUNT(*) FROM verifications"),
        }
