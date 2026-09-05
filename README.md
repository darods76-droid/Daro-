# Wirtschaftskalender-Prognose (EKP)

Eine App, die den **Wirtschaftskalender scannt**, dazu passende **Nachrichten scannt** und
für jeden Termin mit einem **Wahrscheinlichkeitswert** angibt, ob die Konsensprognose durch
die Nachrichtenlage **bestätigt oder widerlegt** wird.

Läuft vollständig mit der Python-Standardbibliothek – kein `pip install`, keine API-Schlüssel
nötig, um loszulegen.

```
2026-09-05 14:00  US  ★★★  US Verbraucherpreise (CPI) y/y   2.9%   ▲ widerlegt (höher)   73%  0.66
2026-09-07 04:00  US  ★★★  Nonfarm Payrolls              165 Tsd.   ▼ widerlegt (tiefer)  47%  0.40
2026-09-06 04:00  EA  ★★★  EZB Zinsentscheid                3.25%   ✔ bestätigt           38%  0.31
```

---

## Schnellstart

```bash
git clone <dieses-repo> && cd Daro-

# 1) Sofort ausprobieren – mit eingebauten Demodaten, ohne Netzzugang
EKP_NEWS_PROVIDER=demo python3 -m ekp scan

# 2) Mit echten Nachrichten (öffentliche RSS-Feeds, keine Schlüssel nötig)
python3 -m ekp scan

# 3) Weboberfläche
./run.sh                 # oder: python3 -m ekp serve
```

Die Oberfläche liegt danach auf <http://127.0.0.1:8000>.

---

## Wie die Bewertung zustande kommt

Die App rät nicht anhand allgemeiner Stimmung, sondern bildet ab, **welches Nachrichtenthema
welchen Indikator in welche Richtung treibt**. Der Weg einer Meldung bis zur Wahrscheinlichkeit:

**1. Kalender scannen.** Jeder Termin wird einer *Indikator-Familie* zugeordnet
(Verbraucherpreise, Beschäftigung, Arbeitslosenquote, BIP, PMI, Stimmung, Einzelhandel,
Industrie, Zinsentscheid, Handelsbilanz, Immobilien, Rohöllager …).

**2. Nachrichten scannen.** Aus 15 öffentlichen RSS-Feeds (deutsch und englisch) werden
Schlagzeilen und Anrisstexte geholt und auf Signale untersucht. Zwei Schichten arbeiten
zusammen:

* eine **Phrasenschicht** für feste Wendungen (`Ölpreise steigen`, `beats expectations`),
* eine **Näherungsschicht**, die erst die *Entität* sucht (`Ölpreis`, `retail sales`,
  `mortgage rates`) und dann im Umfeld ein Richtungswort. Damit werden auch frei
  formulierte Schlagzeilen erfasst.

Negationen (`keine Zinserhöhung` → Gegenrichtung), Verstärker (`massiv`) und Abschwächer
(`leicht`) verändern die Signalstärke. Kursmeldungen zu einzelnen Aktien und Sammelformate
(Ticker, Liveblogs) werden ausgeschlossen – sie sagen nichts über die Konjunktur.

**3. Signal → Richtung für diesen Termin.** Erst die Familie übersetzt ein Thema in eine
Richtung. Dieselbe Meldung wirkt je nach Indikator entgegengesetzt:

| Meldung | Verbraucherpreise | Nonfarm Payrolls | Arbeitslosenquote |
|---|---|---|---|
| „Ölpreise steigen deutlich“ | ▲ höher (+0,95) | – | – |
| „Massiver Stellenabbau“ | – | ▼ tiefer (−1,00) | ▲ höher (+0,95) |
| „EZB straffere Geldpolitik“ | ▼ tiefer (−0,20) | – | – |

**4. Gewichten.** Jeder Beleg wird multipliziert mit
*Relevanz* × *Quellenverlässlichkeit* × *Aktualität*.

* **Relevanz**: Der Wirtschaftsraum wirkt als Filter – eine Meldung über die Eurozone belegt
  keinen US-Termin. Ausnahme sind global wirkende Treiber (Energie, Nahrungsmittel,
  Lieferketten): der Ölpreis treibt die Teuerung in jedem Land.
* **Aktualität**: Halbwertszeit 36 Stunden, gemessen am *Alter der Meldung*. Meldungen nach
  dem Termin fließen nicht ein – sie können eine Prognose nicht mehr vorab prüfen.
* **Titel vor Anriss**: Treffer in der Schlagzeile zählen voll, im Anrisstext zu 55 %.

**5. Wahrscheinlichkeit.** Die gewichteten Belege werden zu einer erwarteten Abweichung
μ verdichtet (in Sigma-Einheiten, über `tanh` begrenzt, damit eine Flut gleichgerichteter
Meldungen die Prognose nicht beliebig kippt). Um μ liegt eine Normalverteilung; ein
Toleranzband ±τ definiert, wann die Prognose als getroffen gilt:

```
P(bestätigt)  = P(−τ < Z < +τ)      Z ~ N(μ, 1)
P(höher)      = P(Z > +τ)
P(tiefer)     = P(Z < −τ)
```

Ohne jede Evidenz ergibt das 31 % / 38 % / 31 % – die ehrliche Ausgangslage, nicht 50/50.

**6. Urteil.** Die größte der drei Wahrscheinlichkeiten bestimmt das Urteil. Zusätzlich wird
eine **Konfidenz** aus Belegmenge, Quellenvielfalt und Einigkeit der Signale berechnet.
Liegt sie unter 0,25, lautet das Urteil bewusst `unbestätigt`: eine dünne Nachrichtenlage
ist kein Beleg, weder dafür noch dagegen.

**7. Gegenprüfung.** Sobald der Ist-Wert vorliegt, vergleicht die App ihr Urteil mit der
tatsächlichen Abweichung und schreibt Trefferquote und Brier-Score fort (`ekp score`).
Aus den geprüften Terminen lernt sie je Familie eine kleine **Vorspannung**, die – stark zur
Null geschrumpft – in künftige Bewertungen einfließt.

---

## Kommandozeile

```bash
python3 -m ekp scan                    # scannen, bewerten, speichern
python3 -m ekp scan --hours 48 --min-importance 3
python3 -m ekp list --all              # auch vergangene Termine
python3 -m ekp list --verdict WIDERLEGT_HOEHER
python3 -m ekp show "Verbraucherpreise"   # Detail inkl. aller Belege mit Links
python3 -m ekp news --hours 24         # gescannte Nachrichten
python3 -m ekp verify                  # Urteile gegen Ist-Werte prüfen
python3 -m ekp score                   # Trefferquote und Brier-Score
python3 -m ekp serve --port 8000       # Weboberfläche
```

Jeder Befehl kennt `--json` für die Weiterverarbeitung.

## Weboberfläche

Karten je Termin mit Urteil, Wahrscheinlichkeitsband (höher / trifft zu / tiefer), Konfidenz,
Prognose-, Vor- und Ist-Wert sowie ausklappbaren Belegen mit Quelle, Zeitstempel, erkannten
Signalen und Link zum Original. Filter nach Urteil, Umschalter für vergangene Termine,
Trefferquote im Kopfbereich. Hell- und Dunkelmodus folgen dem System.

## JSON-API

| Route | Zweck |
|---|---|
| `GET /api/health` | Status und aktive Datenquellen |
| `GET /api/assessments?upcoming=1` | Bewertungen inkl. Belegen |
| `GET /api/scoreboard` | Trefferquote, Brier-Score, gelernte Vorspannungen |
| `GET /api/news?hours=96` | gescannte Nachrichten |
| `POST /api/scan` | Durchlauf anstoßen |

---

## Konfiguration

Alle Einstellungen laufen über Umgebungsvariablen oder eine `.env` (Vorlage:
[`.env.example`](.env.example)).

| Variable | Vorgabe | Bedeutung |
|---|---|---|
| `EKP_CALENDAR_PROVIDER` | `demo` | `demo`, `tradingeconomics`, `fmp` |
| `EKP_NEWS_PROVIDER` | `rss` | `rss`, `newsapi`, `demo` |
| `EKP_TE_KEY` | `guest:guest` | Trading-Economics-Schlüssel |
| `EKP_FMP_KEY` | – | Financial Modeling Prep |
| `EKP_NEWSAPI_KEY` | – | NewsAPI.org |
| `EKP_RSS_FEEDS` | eingebaute Liste | eigene Feeds: `url\|Name\|Gewicht`, komma­getrennt |
| `EKP_LOOKAHEAD_HOURS` | `72` | Vorlauf des Kalenderscans |
| `EKP_NEWS_LOOKBACK_HOURS` | `96` | Rückblick des Nachrichtenscans |
| `EKP_MIN_IMPORTANCE` | `2` | Mindestwichtigkeit (1–3) |
| `EKP_CONFIRM_BAND` | `0.5` | Toleranzband τ in Sigma |
| `EKP_EVIDENCE_SCALE` | `3.0` | Dämpfung der Evidenz (größer = konservativer) |
| `EKP_DB` | `data/ekp.sqlite3` | Speicherort |
| `EKP_OFFLINE` | `0` | erzwingt Demodaten |

### Datenquellen

**Kalender.** `demo` liefert einen realistischen Beispielkalender ohne Netzzugang.
`tradingeconomics` funktioniert mit dem kostenlosen Gast-Schlüssel `guest:guest`
(eingeschränkter Ausschnitt), `fmp` braucht einen eigenen Schlüssel.

**Nachrichten.** Voreingestellt sind 15 öffentliche Feeds von WSJ, Financial Times,
MarketWatch, Yahoo Finance, Investing.com, tagesschau, Handelsblatt, FAZ, WirtschaftsWoche,
Spiegel, SZ sowie den Presseseiten von EZB und Fed. Nicht erreichbare Feeds werden
übersprungen und im Scanbericht als Warnung ausgewiesen.

---

## Tests

```bash
python3 -m unittest discover -s tests -t .    # 90 Tests, ohne Zusatzpakete
pytest                                        # falls pytest installiert ist
```

## Projektaufbau

```
ekp/
  cli.py            Kommandozeile
  server.py         Webserver und JSON-API (Standardbibliothek)
  pipeline.py       Gesamtdurchlauf: scannen → bewerten → prüfen
  store.py          SQLite: Termine, Nachrichten, Urteile, Trefferbilanz
  models.py         Datenmodelle
  config.py         Einstellungen und .env-Loader
  analysis/
    taxonomy.py     Indikator-Familien und ihre Treiber
    lexicon.py      Signalerkennung (Phrasen- und Näherungsschicht)
    relevance.py    Länder- und Themenbezug
    scoring.py      Nachricht → gewichtete Evidenz
    probability.py  Evidenz → Wahrscheinlichkeiten
    engine.py       Orchestrierung
  providers/        Kalender- und Nachrichtenquellen
  web/              Oberfläche (HTML, CSS, JS – ohne Framework)
tests/              90 Tests
```

---

## Grenzen des Verfahrens

* Die Signalerkennung arbeitet regelbasiert auf Schlagzeilen und Anrisstexten. Ironie,
  Verweise auf frühere Zeiträume und komplexe Satzstrukturen erkennt sie nicht zuverlässig.
* Die Treiber-Gewichte sind fachlich begründet, aber gesetzt – nicht aus Daten geschätzt.
  Die Gegenprüfung (`ekp score`) macht die tatsächliche Qualität sichtbar; nutzen Sie sie.
* An nachrichtenarmen Tagen lautet das Urteil überwiegend `unbestätigt`. Das ist kein
  Fehler, sondern das gewünschte Verhalten: ohne Belege gibt es kein Urteil.
* Ein Wahrscheinlichkeitswert ist eine Modellschätzung, keine Vorhersage.

**Keine Anlageberatung.** Die App wertet öffentlich zugängliche Nachrichten aus und trifft
keine Aussage über Kursentwicklungen. Prüfen Sie die Nutzungsbedingungen der Feeds und APIs,
bevor Sie sie über den privaten Gebrauch hinaus verwenden.

## Lizenz

MIT
