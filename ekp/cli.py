"""Kommandozeile der Wirtschaftskalender-Prognose."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta

from .config import get_settings
from .models import Assessment, utcnow
from .pipeline import scan, verify
from .store import Store

# ── Terminalausgabe ──────────────────────────────────────────────────────────
_ANSI = {"reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
         "green": "\033[32m", "red": "\033[31m", "yellow": "\033[33m",
         "blue": "\033[34m", "grey": "\033[90m"}

VERDICT_STYLE = {
    "BESTAETIGT": ("green", "✔"),
    "WIDERLEGT_HOEHER": ("red", "▲"),
    "WIDERLEGT_NIEDRIGER": ("red", "▼"),
    "UNBESTAETIGT": ("grey", "·"),
}

# Kurzform fuer die Tabellenansicht.
SHORT_LABELS = {
    "BESTAETIGT": "bestätigt",
    "WIDERLEGT_HOEHER": "widerlegt (höher)",
    "WIDERLEGT_NIEDRIGER": "widerlegt (tiefer)",
    "UNBESTAETIGT": "unbestätigt",
}


def _use_color() -> bool:
    return sys.stdout.isatty()


def c(text: str, *styles: str) -> str:
    if not _use_color():
        return text
    return "".join(_ANSI.get(s, "") for s in styles) + text + _ANSI["reset"]


def bar(p: float, width: int = 14) -> str:
    filled = int(round(p * width))
    return "█" * filled + "░" * (width - filled)


def fmt_value(value: float | None, unit: str = "") -> str:
    if value is None:
        return "–"
    text = f"{value:g}"
    return f"{text}{unit}" if unit == "%" else (f"{text} {unit}".strip())


def print_assessment_table(rows: list[dict], title: str) -> None:
    print()
    print(c(f"── {title} ", "bold") + c("─" * max(0, 96 - len(title)), "dim"))
    if not rows:
        print(c("   (keine Einträge)", "dim"))
        return
    header = (f"{'Zeit (UTC)':<18}{'L':<4}{'Wi.':<5}{'Termin':<36}{'Prognose':>12}"
              f"   {'Urteil':<20}{'Wahrsch.':>9}  Konf.")
    print(c(header, "dim"))
    for row in rows:
        ev = row["event"]
        when = str(ev["when"])[:16].replace("T", " ")
        color, glyph = VERDICT_STYLE.get(row["verdict"], ("grey", "·"))
        label = SHORT_LABELS.get(row["verdict"], row["verdict"])
        stars = "★" * int(ev.get("importance") or 0)
        prob = row["headline_probability"]
        forecast = fmt_value(ev.get("forecast"), ev.get("unit") or "")[:12]
        line = (f"{when:<18}{(ev.get('country') or ''):<4}{stars:<5}{ev['title'][:34]:<36}"
                f"{forecast:>12}   "
                f"{glyph} {label:<18}{prob:>8.0%}  {row['confidence']:.2f}")
        print(c(line, color))
        if row.get("verification"):
            v = row["verification"]
            hit = {1: c("Treffer", "green"), 0: c("daneben", "red")}.get(v.get("hit"), c("n/a", "grey"))
            print(c(f"    → Ist-Wert {fmt_value(ev.get('actual'), ev.get('unit') or '')}, "
                    f"Abweichung {v['z']:+.2f} σ ({v['outcome']}) – {hit}", "dim"))
    print()


def print_detail(row: dict) -> None:
    ev = row["event"]
    color, glyph = VERDICT_STYLE.get(row["verdict"], ("grey", "·"))
    print()
    print(c(f"{ev['title']}  [{ev.get('country')}]", "bold"))
    print(c(f"Termin: {str(ev['when'])[:16].replace('T', ' ')} UTC   "
            f"Wichtigkeit: {'★' * int(ev.get('importance') or 0)}   "
            f"Familie: {row['family']}", "dim"))
    print(f"Prognose: {fmt_value(ev.get('forecast'), ev.get('unit') or '')}   "
          f"Vorwert: {fmt_value(ev.get('previous'), ev.get('unit') or '')}   "
          f"Ist: {fmt_value(ev.get('actual'), ev.get('unit') or '')}")
    print()
    print(c(f"{glyph} {Assessment.VERDICT_LABELS.get(row['verdict'], row['verdict'])} "
            f"— {row['headline_probability']:.0%}", color, "bold"))
    print(f"   erwartete Abweichung: {row['expected_surprise']:+.2f} σ    "
          f"Konfidenz: {row['confidence']:.0%}")
    print()
    print(f"   höher als Prognose   {bar(row['p_above'])} {row['p_above']:>6.1%}")
    print(f"   Prognose trifft zu   {bar(row['p_confirm'])} {row['p_confirm']:>6.1%}")
    print(f"   tiefer als Prognose  {bar(row['p_below'])} {row['p_below']:>6.1%}")
    for note in row.get("notes", []):
        print(c(f"   ℹ {note}", "dim"))

    print()
    print(c(f"Belegende Nachrichten ({len(row['evidence'])}):", "bold"))
    if not row["evidence"]:
        print(c("   keine", "dim"))
    for e in row["evidence"]:
        arrow = c("▲", "red") if e["direction"] > 0 else c("▼", "blue")
        print(f"  {arrow} {e['strength']:.2f}  {e['headline'][:78]}")
        print(c(f"      {e['source']} · {str(e['published'])[:16].replace('T', ' ')} · "
                f"{', '.join(e['signals'])}", "dim"))
        if e.get("url"):
            print(c(f"      {e['url']}", "dim"))
    print()


# ── Befehle ──────────────────────────────────────────────────────────────────
def cmd_scan(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.provider:
        settings.calendar_provider = args.provider
    if args.news:
        settings.news_provider = args.news
    if args.hours:
        settings.lookahead_hours = args.hours
    if args.min_importance:
        settings.min_importance = args.min_importance

    with Store(settings.db_path) as store:
        report = scan(settings, store)
        if args.json:
            print(json.dumps({"summary": report.summary(),
                              "assessments": [a.to_dict() for a in report.assessments]},
                             indent=2, ensure_ascii=False))
            return 0
        s = report.summary()
        print(c(f"\nKalender: {s['calendar_provider']} · {s['events_found']} Termine "
                f"({s['events_kept']} relevant)   "
                f"Nachrichten: {s['news_provider']} · {s['news_found']} neu, "
                f"{s['news_pool']} im Pool", "dim"))
        for w in s["warnings"]:
            print(c(f"  ⚠ {w}", "yellow"))
        rows = store.latest_assessments(upcoming_only=True)
        print_assessment_table(rows, "Anstehende Termine")
        counts = " · ".join(f"{Assessment.VERDICT_LABELS.get(k, k)}: {v}"
                            for k, v in sorted(s["verdicts"].items()))
        print(c(f"  {counts}\n", "dim"))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    settings = get_settings()
    with Store(settings.db_path) as store:
        rows = store.latest_assessments(upcoming_only=not args.all)
        if args.verdict:
            rows = [r for r in rows if r["verdict"] == args.verdict.upper()]
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            return 0
        print_assessment_table(rows, "Alle Termine" if args.all else "Anstehende Termine")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    settings = get_settings()
    with Store(settings.db_path) as store:
        rows = store.latest_assessments(upcoming_only=False, limit=1000)
        match = [r for r in rows
                 if r["event"]["event_id"].startswith(args.event_id)
                 or args.event_id.lower() in r["event"]["title"].lower()]
        if not match:
            print(c(f"Kein Termin gefunden für '{args.event_id}'.", "red"))
            return 1
        if args.json:
            print(json.dumps(match[0] if len(match) == 1 else match, indent=2, ensure_ascii=False))
            return 0
        for row in match[:3]:
            print_detail(row)
    return 0


def cmd_news(args: argparse.Namespace) -> int:
    settings = get_settings()
    with Store(settings.db_path) as store:
        items = store.news_since(utcnow() - timedelta(hours=args.hours))
        if args.json:
            print(json.dumps([n.to_dict() for n in items], indent=2, ensure_ascii=False))
            return 0
        print()
        print(c(f"── Gescannte Nachrichten ({len(items)}) ", "bold"))
        for n in items[:args.limit]:
            print(f"  {str(n.published)[:16]}  {c(n.source[:22], 'dim'):<30} {n.title[:80]}")
        print()
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    settings = get_settings()
    with Store(settings.db_path) as store:
        results = verify(settings, store)
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return 0
        print()
        if not results:
            print(c("  Keine neuen Termine zum Gegenprüfen.", "dim"))
        for r in results:
            mark = {1: c("Treffer", "green"), 0: c("daneben", "red")}.get(r["hit"], c("n/a", "grey"))
            print(f"  {r['title'][:44]:<46} Prognose {r['forecast']:g} → Ist {r['actual']:g}  "
                  f"({r['z']:+.2f} σ, {r['outcome']})   Urteil {r['verdict']:<20} {mark}")
        print()
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    settings = get_settings()
    with Store(settings.db_path) as store:
        board = store.scoreboard()
        if args.json:
            print(json.dumps({**board, "counts": store.counts(),
                              "priors": store.family_priors()}, indent=2, ensure_ascii=False))
            return 0
        counts = store.counts()
        print()
        print(c("── Trefferquote der bisherigen Urteile ", "bold"))
        print(f"  Datenbestand: {counts['events']} Termine · {counts['news']} Nachrichten · "
              f"{counts['assessments']} Bewertungen · {counts['verifications']} geprüft")
        if not board["n"]:
            print(c("  Noch keine überprüften Termine – nach der ersten Veröffentlichung "
                    "erscheint hier die Trefferquote.", "dim"))
        else:
            hr = board["hit_rate"]
            print(f"  Geprüft: {board['n']} Termine, davon {board['n_scored']} mit "
                  f"eindeutigem Urteil (unbestätigte Fälle zählen nicht)")
            print(f"  Trefferquote: {hr:.0%}" if hr is not None
                  else c("  Trefferquote: noch kein eindeutiges Urteil überprüft", "dim"))
            print(f"  Brier-Score:  {board['brier']:.3f}  (0 = perfekt, niedriger ist besser)")
            print()
            for row in board["by_family"]:
                hitrate = f"{row['hitrate']:.0%}" if row["hitrate"] is not None else "n/a"
                print(f"    {row['family']:<20} n={row['n']:<4} Treffer {hitrate:>5}  "
                      f"Brier {row['brier']:.3f}  ø-Abweichung {row['mean_z']:+.2f} σ")
        print()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve
    serve(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ekp",
        description="Scannt den Wirtschaftskalender und prüft die Konsensprognosen "
                    "gegen die aktuelle Nachrichtenlage.")
    p.add_argument("--json", action="store_true", help="Ausgabe als JSON")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="Kalender und Nachrichten scannen und bewerten")
    s.add_argument("--provider", help="Kalenderquelle: demo | tradingeconomics | fmp")
    s.add_argument("--news", help="Nachrichtenquelle: rss | newsapi | demo")
    s.add_argument("--hours", type=int, help="Vorlauf in Stunden")
    s.add_argument("--min-importance", type=int, choices=[1, 2, 3], dest="min_importance")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    l = sub.add_parser("list", help="Gespeicherte Bewertungen anzeigen")
    l.add_argument("--all", action="store_true", help="auch vergangene Termine")
    l.add_argument("--verdict", help="nach Urteil filtern")
    l.add_argument("--json", action="store_true")
    l.set_defaults(func=cmd_list)

    sh = sub.add_parser("show", help="Einen Termin im Detail mit allen Belegen")
    sh.add_argument("event_id", help="Termin-ID oder Teil des Titels")
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(func=cmd_show)

    n = sub.add_parser("news", help="Gescannte Nachrichten auflisten")
    n.add_argument("--hours", type=int, default=96)
    n.add_argument("--limit", type=int, default=40)
    n.add_argument("--json", action="store_true")
    n.set_defaults(func=cmd_news)

    v = sub.add_parser("verify", help="Urteile gegen die veröffentlichten Ist-Werte prüfen")
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=cmd_verify)

    sc = sub.add_parser("score", help="Trefferquote und Brier-Score")
    sc.add_argument("--json", action="store_true")
    sc.set_defaults(func=cmd_score)

    sv = sub.add_parser("serve", help="Weboberfläche starten")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--no-browser", action="store_true")
    sv.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
