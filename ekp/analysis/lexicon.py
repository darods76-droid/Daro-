"""Nachrichten-Lexikon.

Erkennt in Schlagzeilen und Anrissen thematische Signale und deren Richtung.
Ein Treffer sagt: "Thema X bewegt sich nach oben/unten." Erst die Taxonomie
uebersetzt das in eine Richtung fuer einen konkreten Kalendertermin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .textutil import fold


@dataclass(frozen=True)
class SignalHit:
    group: str
    direction: int      # +1 = Thema steigt/verstaerkt sich, -1 = faellt/schwaecht ab
    strength: float
    term: str

    @property
    def signed(self) -> float:
        return self.direction * self.strength


# (Muster, Signalgruppe, Richtung, Grundstaerke)
# Muster werden gegen den ASCII-normalisierten Text geprueft.
RULES: tuple[tuple[str, str, int, float], ...] = (
    # ── Energie ───────────────────────────────────────────────────────────────
    (r"(oel|benzin|diesel|gas|strom|energie|rohoel|brent|wti|heizoel)preis\w*\s+(steig|klettern|zieh|leg\w* zu|anzieh)", "energiepreise", +1, 1.0),
    (r"(oel|benzin|gas|strom|energie|rohoel|brent|wti)preis\w*\s+(fall|sink|geb\w* nach|rutsch|bricht ein)", "energiepreise", -1, 1.0),
    (r"(oil|gas|energy|fuel|petrol|gasoline|electricity) prices? (rise|rises|jump|surge|climb|soar|spike)", "energiepreise", +1, 1.0),
    (r"(oil|gas|energy|fuel|petrol|gasoline|electricity) prices? (fall|drop|slump|tumble|slide|plunge|ease)", "energiepreise", -1, 1.0),
    (r"(opec|opec\+)[\s\-]*(kuerz|drossel|cut|reduce)", "energiepreise", +1, 0.9),
    (r"(opec|opec\+)[\s\-]*(erhoeh|weitet aus|boost|raise|increase output)", "energiepreise", -1, 0.8),
    (r"(gaspreis|strompreis|energiekosten)\w*\s*(rekord|explod|schnellen)", "energiepreise", +1, 1.1),
    (r"(oil|brent|wti|crude)\s*(rally|rallies|hits? .{0,12}high)", "energiepreise", +1, 0.9),
    (r"(oil|brent|wti|crude)\s*(hits? .{0,12}low|sinks?)", "energiepreise", -1, 0.9),

    # ── Nahrungsmittel ────────────────────────────────────────────────────────
    (r"(lebensmittel|nahrungsmittel|getreide|weizen|kaffee|zucker)preis\w*\s+(steig|klettern|zieh)", "nahrungsmittelpreise", +1, 0.9),
    (r"(lebensmittel|nahrungsmittel|getreide|weizen)preis\w*\s+(fall|sink|geb\w* nach)", "nahrungsmittelpreise", -1, 0.9),
    (r"(food|grain|wheat|crop) prices? (rise|jump|surge|climb|soar)", "nahrungsmittelpreise", +1, 0.9),
    (r"(food|grain|wheat|crop) prices? (fall|drop|ease|slump)", "nahrungsmittelpreise", -1, 0.9),
    (r"(duerre|missernte|ernteausfall|drought|crop failure)", "nahrungsmittelpreise", +1, 0.8),

    # ── Löhne ────────────────────────────────────────────────────────────────
    (r"(lohn|gehalt|tarif)\w*\s*(abschluss|erhoehung|plus|steig|runde)", "loehne", +1, 0.9),
    (r"(wage|pay|salary|earnings) (growth|increase|rise|jump|deal|settlement)", "loehne", +1, 0.9),
    (r"(\bstreik|warnstreik|arbeitskampf|\bwalkout\b|workers? strike)", "loehne", +1, 0.7),
    (r"(lohnzurueckhaltung|nullrunde|wage restraint|pay freeze)", "loehne", -1, 0.8),
    (r"(mindestlohn|minimum wage)\w*\s*(steig|erhoeh|rise|increase)", "loehne", +1, 0.8),

    # ── Arbeitsmarkt ─────────────────────────────────────────────────────────
    (r"(entlassung|stellenabbau|jobabbau|kuendigungswelle|personalabbau|arbeitsplatzabbau)", "entlassungen", +1, 1.0),
    (r"(layoff|job cuts?|cutting jobs|redundanc|slashes? .{0,15}jobs|axes? .{0,15}jobs|downsizing)", "entlassungen", +1, 1.0),
    (r"(insolvenz|pleite|bankruptcy|insolvency|werksschliessung|plant closure)", "entlassungen", +1, 0.9),
    (r"(kurzarbeit|hiring freeze|einstellungsstopp)", "entlassungen", +1, 0.7),
    (r"(stellen\w*aufbau|neueinstellung|einstellungsoffensive|schafft .{0,15}stellen|jobmotor)", "einstellungen", +1, 1.0),
    (r"(hiring (spree|surge|picks? up)|adds? .{0,15}jobs|job creation|recruit\w* drive|expands? workforce)", "einstellungen", +1, 1.0),
    (r"(arbeitskraeftemangel|fachkraeftemangel|labou?r shortage|worker shortage)", "einstellungen", +1, 0.6),
    (r"(arbeitsmarkt\w*\s*(robust|stabil|stark)|labou?r market (resilient|strong|tight))", "einstellungen", +1, 0.7),
    (r"(arbeitsmarkt\w*\s*(schwaech|kuehlt ab|truebt)|labou?r market (cools|weakens|softens))", "entlassungen", +1, 0.8),

    # ── Konsum ───────────────────────────────────────────────────────────────
    (r"(konsum|verbraucher|kauflaune|einzelhandel)\w*\s*(steig|erhol|zieh an|robust|stark|boom)", "konsumnachfrage", +1, 0.9),
    (r"(konsum|verbraucher|kauflaune|einzelhandel)\w*\s*(schwach|brich|einbruch|zurueckhalt|flau|sink)", "konsumnachfrage", -1, 0.9),
    (r"(consumer spending|retail sales|demand) (rises?|jumps?|strong|resilient|rebounds?)", "konsumnachfrage", +1, 0.9),
    (r"(consumer spending|retail sales|demand) (falls?|drops?|weak|slumps?|softens?)", "konsumnachfrage", -1, 0.9),
    (r"(rabattschlacht|discounting|preisnachlaesse)", "konsumnachfrage", -1, 0.6),

    # ── Kredit / Finanzierungsbedingungen ────────────────────────────────────
    (r"(kreditvergabe|kreditbedingung)\w*\s*(verschaerf|strenger|restriktiv|tighten)", "kreditbedingungen", +1, 0.8),
    (r"(banks? tighten|credit (crunch|tightening)|lending standards? tighten)", "kreditbedingungen", +1, 0.8),
    (r"(kreditvergabe|lending)\w*\s*(lockert|ausgeweitet|eases?|loosens?|picks? up)", "kreditbedingungen", -1, 0.7),
    (r"(hypothekenzins|mortgage rate)\w*\s*(steig|klettern|rise|jump)", "kreditbedingungen", +1, 0.8),
    (r"(hypothekenzins|mortgage rate)\w*\s*(fall|sink|drop|ease)", "kreditbedingungen", -1, 0.8),

    # ── Lieferketten ─────────────────────────────────────────────────────────
    (r"(lieferkette|lieferengpass|materialmangel|chipmangel|hafenstau|frachtrate)", "lieferketten", +1, 0.9),
    (r"(supply chain (disruption|snarl|bottleneck)|shipping (costs?|rates?) (surge|jump)|port congestion|freight rates? (soar|jump))", "lieferketten", +1, 0.9),
    (r"(lieferketten\w*\s*(entspann|normalisier)|supply chains? (ease|normalise|normalize|improve))", "lieferketten", -1, 0.8),

    # ── Unternehmensstimmung ─────────────────────────────────────────────────
    (r"(geschaeftsklima|stimmung|zuversicht|optimismus)\w*\s*(hell|verbesser|steig|aufhell)", "unternehmensstimmung", +1, 0.9),
    (r"(geschaeftsklima|stimmung|zuversicht)\w*\s*(truebt|verschlechter|sink|eintruebung|pessimis)", "unternehmensstimmung", -1, 0.9),
    (r"(business (confidence|sentiment|morale)|optimism) (improves?|rises?|rebounds?|brightens?)", "unternehmensstimmung", +1, 0.9),
    (r"(business (confidence|sentiment|morale)|optimism) (falls?|worsens?|deteriorates?|sours?|dims?)", "unternehmensstimmung", -1, 0.9),
    (r"(gewinnwarnung|profit warning|prognose gesenkt|cuts? (its )?outlook|guidance cut)", "unternehmensstimmung", -1, 0.8),
    (r"(prognose angehoben|raises? (its )?outlook|guidance raised|rekordgewinn)", "unternehmensstimmung", +1, 0.7),

    # ── Immobilien ───────────────────────────────────────────────────────────
    (r"(baugenehmigung|wohnungsbau|baubranche)\w*\s*(steig|zieh an|erhol)", "immobilienmarkt", +1, 0.9),
    (r"(baugenehmigung|wohnungsbau|baubranche|immobilienmarkt)\w*\s*(brich|einbruch|krise|sink|flaut)", "immobilienmarkt", -1, 0.9),
    (r"(home sales|housing (market|starts)|construction) (rise|jump|rebound|recover)", "immobilienmarkt", +1, 0.9),
    (r"(home sales|housing (market|starts)|construction) (fall|drop|slump|slide|weaken)", "immobilienmarkt", -1, 0.9),

    # ── Außenhandel ──────────────────────────────────────────────────────────
    (r"(export)\w*\s*(steig|zieh an|boom|wachs)", "aussenhandel", +1, 0.9),
    (r"(export)\w*\s*(brich|einbruch|sink|rueckgang)", "aussenhandel", -1, 0.9),
    (r"(exports?) (rise|jump|surge|rebound|grow)", "aussenhandel", +1, 0.9),
    (r"(exports?) (fall|drop|slump|plunge|decline)", "aussenhandel", -1, 0.9),
    (r"(\bzoellen?\b|\bzoll(satz|erhoehung|streit)|strafzoe?ll|\btariffs?\b|trade war|handelsstreit|handelskonflikt|exportkontroll|\bsanktion)", "aussenhandel", -1, 0.8),
    (r"(handelsabkommen|trade deal|zollsenkung|tariff cut)", "aussenhandel", +1, 0.7),

    # ── Währung ──────────────────────────────────────────────────────────────
    (r"(euro|dollar|pfund|yen|waehrung)\w*\s*(schwaech|faellt|sinkt|unter druck|abgestuerzt|verliert)", "waehrungsschwaeche", +1, 0.7),
    (r"(euro|dollar|pound|yen|currency) (weakens?|falls?|slides?|slumps?|hits? .{0,12}low)", "waehrungsschwaeche", +1, 0.7),
    (r"(euro|dollar|pfund|yen)\w*\s*(erstark|steigt|fester|gewinnt|aufwert)", "waehrungsschwaeche", -1, 0.7),
    (r"(euro|dollar|pound|yen) (strengthens?|rises?|firms?|rallies|gains?)", "waehrungsschwaeche", -1, 0.7),

    # ── Notenbank ────────────────────────────────────────────────────────────
    (r"(zinserhoehung|straffung|restriktiv|hawkish|falken|zinsschritt nach oben|hoehere zinsen)", "notenbank_straff", +1, 1.0),
    (r"(rate hike|tighten\w* policy|hawkish|higher for longer|raises? rates?)", "notenbank_straff", +1, 1.0),
    (r"(zinssenkung|lockerung|dovish|tauben|zinswende nach unten|niedrigere zinsen)", "notenbank_straff", -1, 1.0),
    (r"(rate cut|cuts? rates?|easing cycle|dovish|pivot)", "notenbank_straff", -1, 1.0),
    (r"(inflation\w*\s*(hartnaeckig|zaeh|klebrig)|sticky inflation|inflation persists)", "notenbank_straff", +1, 0.7),

    # ── Wachstum / Rezession ─────────────────────────────────────────────────
    (r"(\brezession|\babschwung\b|wirtschaft \w+ schrumpf|konjunktureinbruch|wirtschaftskrise|\bstagnation)", "wachstum", -1, 1.0),
    (r"(\brecession\b|economic downturn|\bcontraction\b|economy (shrinks?|contracts?)|economic slowdown|\bstagnat)", "wachstum", -1, 1.0),
    (r"(\baufschwung\b|konjunkturelle erholung|wachstumsschub|konjunktur\w*\s*(zieh|erhol|belebt)|konjunkturboom|wirtschaftsboom)", "wachstum", +1, 1.0),
    (r"(economic (recovery|rebound|expansion|upswing)|growth (accelerates?|picks? up)|economy (rebounds?|expands?))", "wachstum", +1, 1.0),
    (r"(prognose\w*\s*(gesenkt|gekappt)|cuts? (growth )?forecast|downgrades? outlook)", "wachstum", -1, 0.8),
    (r"(prognose\w*\s*(angehoben|erhoeht)|raises? (growth )?forecast|upgrades? outlook)", "wachstum", +1, 0.8),

    # ── Industrie ────────────────────────────────────────────────────────────
    (r"(produktion|fertigung|industrie)\w*\s*(steig|hochgefahren|ausgeweitet|zieh an)", "industrieproduktion", +1, 0.9),
    (r"(produktion|fertigung|industrie)\w*\s*(gedrosselt|brich|einbruch|sink|stillstand|heruntergefahren)", "industrieproduktion", -1, 0.9),
    (r"(factory|industrial) (output|production) (rises?|jumps?|expands?|rebounds?)", "industrieproduktion", +1, 0.9),
    (r"(factory|industrial) (output|production) (falls?|drops?|contracts?|slumps?)", "industrieproduktion", -1, 0.9),
    (r"(auftragsbuecher|auftragseingaenge|order books?) (voll|gefuellt|swell|rise|jump)", "industrieproduktion", +1, 0.8),
    (r"(auftragsflaute|auftragsmangel|order (slump|drought)|weak orders)", "industrieproduktion", -1, 0.8),

    # ── Direkte Aussagen zur Prognoseabweichung ──────────────────────────────
    (r"(ueber den erwartungen|besser als erwartet|staerker als erwartet|hoeher als erwartet|uebertrifft die (erwartungen|prognosen)|unerwartet (stark|kraeftig|deutlich))", "direkt_hoeher", +1, 1.4),
    (r"(beats? (expectations|forecasts?|estimates?)|(stronger|higher|hotter|better) than (expected|forecast)|tops? (estimates|forecasts?)|upside surprise)", "direkt_hoeher", +1, 1.4),
    (r"(unter den erwartungen|schwaecher als erwartet|niedriger als erwartet|verfehlt die (erwartungen|prognosen)|enttaeuscht)", "direkt_niedriger", +1, 1.4),
    (r"(miss(es)? (expectations|forecasts?|estimates?)|(weaker|lower|cooler|worse) than (expected|forecast)|falls? short|downside surprise|disappoints?)", "direkt_niedriger", +1, 1.4),
    (r"(oekonomen (rechnen|erwarten) mit .{0,25}(anstieg|zunahme|beschleunigung)|analysten erwarten .{0,20}(hoeher|mehr))", "direkt_hoeher", +1, 0.8),
    (r"(oekonomen (rechnen|erwarten) mit .{0,25}(rueckgang|abnahme|abschwaechung)|analysten erwarten .{0,20}(niedriger|weniger))", "direkt_niedriger", +1, 0.8),
    (r"(economists? (expect|see|forecast) .{0,25}(rise|increase|pickup|acceleration))", "direkt_hoeher", +1, 0.8),
    (r"(economists? (expect|see|forecast) .{0,25}(fall|decline|drop|slowdown))", "direkt_niedriger", +1, 0.8),

    # ── Generische Bewertung (wird ueber good_is_up der Familie uebersetzt) ──
    (r"(\blichtblick|\baufatmen\b|\bzuversichtlich|\berfreulich|ueberraschend gut)", "gute_nachricht", +1, 0.35),
    (r"(\bdaempfer\b|\brueckschlag\b|konjunktursorge|\bduestere|\bhiobsbotschaft|besorgniserregend)", "schlechte_nachricht", +1, 0.35),
    (r"(\bupbeat\b|\bencouraging\b|bright spot|\breassuring\b)", "gute_nachricht", +1, 0.35),
    (r"(\bgloomy\b|\bgrim\b|\bworrying\b|\bsetback\b|warning sign|\bbleak\b)", "schlechte_nachricht", +1, 0.35),
)

_COMPILED: tuple[tuple[re.Pattern[str], str, int, float], ...] = tuple(
    (re.compile(pat), group, direction, strength) for pat, group, direction, strength in RULES
)

# Verstaerker / Abschwaecher im Umfeld eines Treffers.
_INTENSIFIERS = re.compile(
    r"(stark|deutlich|kraeftig|massiv|drastisch|sprunghaft|rekord|explod|dramatisch|"
    r"surge|soar|plunge|slump|tumble|spike|sharply|record|steep)"
)
_DIMINISHERS = re.compile(
    r"(leicht|etwas|moderat|geringfuegig|minimal|kaum|verhalten|slightly|modest|marginal|edges?)"
)
# Verneinung unmittelbar vor dem Treffer.
_NEGATIONS = re.compile(r"(kein\w*|nicht|nie |ohne |entgegen|dementiert|abgesagt|no |not |denies?|rules? out)\s*$")

_WINDOW = 34   # Zeichen vor/nach dem Treffer, die den Kontext liefern


# ─────────────────────────────────────────────────────────────────────────────
# Naeherungsschicht: Entitaet + Richtungswort
#
# Die Regeln oben verlangen feste Wortfolgen ("oelpreise steigen"). Echte
# Schlagzeilen formulieren freier ("Ölpreis klettert nach OPEC-Treffen deutlich
# nach oben"). Diese Schicht sucht deshalb erst die *Entitaet* (das
# makrooekonomische Thema) und dann in ihrem Umfeld ein *Richtungswort*.
# Die Entitaet bleibt Pflicht - dadurch bleibt die Trefferqualitaet hoch.
# ─────────────────────────────────────────────────────────────────────────────

_DIR_UP = re.compile(
    r"(steig|klettert|klettern|zieht an|ziehen an|legt zu|legen zu|verteuer|teurer|"
    r"anstieg|zunahme|zulegen|zugelegt|sprunghaft|rekordhoch|explodier|"
    r"surges?|jumps?|rises?|rising|climbs?|soars?|spikes?|higher|gains?|advances?|"
    r"rallies|rallied|accelerat|picks? up|strengthens?)")
_DIR_DOWN = re.compile(
    r"(faellt|fallen|sinkt|sinken|gibt nach|geben nach|rutsch|billiger|guenstiger|"
    r"rueckgang|abnahme|einbruch|bricht ein|brechen ein|verbilligt|schrumpf|schwaech|"
    r"falls?|fell|drops?|declines?|slides?|slumps?|tumbles?|plunges?|lower|"
    r"eases?|retreats?|weakens?|cools?|softens?|contracts?)")

_PROX_WINDOW = 75      # Zeichen um die Entitaet, in denen das Richtungswort zaehlt

# Kursmeldungen zu einzelnen Wertpapieren sind keine Konjunkturnachrichten:
# "Ölkonzern-Aktie faellt" sagt nichts ueber den Oelpreis.
_MARKET_NOISE = re.compile(
    r"(\baktie|\baktien|\bshares?\b|\bstocks?\b|\bkurs(e|ziel)?\b|boersengang|\bipo\b|"
    r"quartalszahlen|\bearnings\b|analyst\w* (stuft|rating)|\bdividende)")

# (Entitaetsmuster, Signalgruppe, Vorzeichen, Grundstaerke)
# Vorzeichen +1: Entitaet steigt => Gruppe steigt. -1: umgekehrt.
PROXIMITY_RULES: tuple[tuple[str, str, int, float], ...] = (
    (r"(oelpreis|benzinpreis|dieselpreis|gaspreis|strompreis|energiepreis|energiekosten|"
     r"heizoelpreis|rohoelpreis|brent|wti|crude( oil)?|oil price|gas price|"
     r"energy (price|cost)|fuel price|gasoline price|electricity price|\boil\b|\bbenzin\b)",
     "energiepreise", +1, 0.85),
    (r"(lebensmittelpreis|nahrungsmittelpreis|getreidepreis|weizenpreis|kaffeepreis|"
     r"food price|grain price|wheat price|crop price)", "nahrungsmittelpreise", +1, 0.8),
    (r"(loehne|lohnkosten|gehaelter|tariflohn|lohnwachstum|lohnplus|"
     r"wages?|pay growth|salaries|earnings growth|labou?r costs?)", "loehne", +1, 0.8),
    (r"(konsum|kauflaune|verbrauchernachfrage|einzelhandelsumsaetze|"
     r"consumer (spending|demand)|retail sales|household spending)",
     "konsumnachfrage", +1, 0.85),
    (r"(geschaeftsklima|unternehmensstimmung|konjunkturstimmung|ifo|zew|"
     r"business (confidence|sentiment|morale)|economic sentiment|pmi|"
     r"purchasing managers|consumer confidence|verbrauchervertrauen)",
     "unternehmensstimmung", +1, 0.85),
    (r"(wohnungsbau|baugenehmigungen|baubeginne|immobilienmarkt|hausverkaeufe|"
     r"housing (starts|market)|home sales|building permits|construction activity)",
     "immobilienmarkt", +1, 0.8),
    (r"(exporte|ausfuhren|importe|einfuhren|aussenhandel|"
     r"exports?|imports?|trade volume)", "aussenhandel", +1, 0.8),
    (r"(industrieproduktion|fabrikproduktion|auftragseingaenge|auftragsbestand|"
     r"industrial (output|production)|factory (output|orders)|manufacturing output)",
     "industrieproduktion", +1, 0.85),
    (r"(hypothekenzins|bauzins|kreditzins|anleiherendite|renditen|"
     r"mortgage rates?|bond yields?|borrowing costs?|lending rates?)",
     "kreditbedingungen", +1, 0.8),
    (r"(konjunktur|wirtschaftsleistung|wirtschaftswachstum|"
     r"economic (growth|activity|output)|the economy)", "wachstum", +1, 0.8),
    (r"(frachtraten|lieferzeiten|transportkosten|"
     r"freight rates?|shipping costs?|delivery times)", "lieferketten", +1, 0.75),
    # Waehrung: ein *stark* aufwertender Euro bedeutet *weniger* Waehrungsschwaeche.
    (r"(euro|dollar|pfund|yen|greenback|sterling)",
     "waehrungsschwaeche", -1, 0.6),
    # Stellen: "Zahl der Jobs steigt" -> Einstellungen; "faellt" -> Entlassungen.
    (r"(beschaeftigung|stellenzahl|zahl der (jobs|stellen)|arbeitsplaetze|"
     r"payrolls|employment|job growth|hiring)", "einstellungen", +1, 0.85),
    (r"(arbeitslosigkeit|arbeitslosenzahl|erwerbslosigkeit|"
     r"unemployment|jobless claims|layoffs)", "entlassungen", +1, 0.85),
)

_PROX_COMPILED = tuple((re.compile(pat), grp, sign, base)
                       for pat, grp, sign, base in PROXIMITY_RULES)


def _proximity_signals(folded: str) -> list[SignalHit]:
    """Sucht Entitaeten und wertet das naechstgelegene Richtungswort aus."""
    hits: list[SignalHit] = []
    for pattern, group, sign, base in _PROX_COMPILED:
        match = pattern.search(folded)
        if not match:
            continue
        start, end = match.span()
        window = folded[max(0, start - _PROX_WINDOW):min(len(folded), end + _PROX_WINDOW)]

        if _MARKET_NOISE.search(window):
            continue                      # Kursmeldung, keine Konjunkturaussage

        up, down = _DIR_UP.search(window), _DIR_DOWN.search(window)
        if bool(up) == bool(down):
            continue                      # keine oder widerspruechliche Richtung

        direction = sign if up else -sign
        factor = 1.0
        if _INTENSIFIERS.search(window):
            factor *= 1.3
        if _DIMINISHERS.search(window):
            factor *= 0.7
        if _NEGATIONS.search(folded[max(0, start - _WINDOW):start]):
            direction, factor = -direction, factor * 0.8

        hits.append(SignalHit(group=group, direction=direction,
                              strength=round(base * factor, 4),
                              term=match.group(0)[:60]))
    return hits


def extract_signals(text: str) -> list[SignalHit]:
    """Findet alle thematischen Signale in einem Text."""
    folded = fold(text)
    if not folded:
        return []

    hits: dict[tuple[str, int], SignalHit] = {}
    for pattern, group, direction, strength in _COMPILED:
        match = pattern.search(folded)
        if not match:
            continue

        start, end = match.span()
        before = folded[max(0, start - _WINDOW):start]
        around = folded[max(0, start - _WINDOW):min(len(folded), end + _WINDOW)]

        factor = 1.0
        if _INTENSIFIERS.search(around):
            factor *= 1.35
        if _DIMINISHERS.search(around):
            factor *= 0.65

        eff_direction = direction
        if _NEGATIONS.search(before):
            eff_direction = -direction
            factor *= 0.8

        hit = SignalHit(group=group, direction=eff_direction,
                        strength=round(strength * factor, 4), term=match.group(0)[:80])

        # Pro Gruppe und Richtung nur der staerkste Treffer - sonst wuerden
        # Wiederholungen derselben Aussage die Evidenz kuenstlich aufblaehen.
        key = (group, eff_direction)
        if key not in hits or hit.strength > hits[key].strength:
            hits[key] = hit

    for hit in _proximity_signals(folded):
        key = (hit.group, hit.direction)
        if key not in hits or hit.strength > hits[key].strength:
            hits[key] = hit

    return sorted(hits.values(), key=lambda h: -h.strength)


# Treffer in der Zusammenfassung sind unzuverlaessiger als in der Schlagzeile:
# Anrisstexte enthalten oft Nebenthemen, Boersenkurse und Randbemerkungen.
SUMMARY_WEIGHT = 0.55


def extract_from_item(title: str, summary: str = "") -> list[SignalHit]:
    """Signale einer Meldung - Schlagzeile voll, Anrisstext abgeschwaecht."""
    merged: dict[tuple[str, int], SignalHit] = {}

    def absorb(hits: list[SignalHit], factor: float) -> None:
        for hit in hits:
            scaled = hit if factor == 1.0 else SignalHit(
                group=hit.group, direction=hit.direction,
                strength=round(hit.strength * factor, 4), term=hit.term)
            key = (scaled.group, scaled.direction)
            if key not in merged or scaled.strength > merged[key].strength:
                merged[key] = scaled

    absorb(extract_signals(title), 1.0)
    if summary:
        absorb(extract_signals(summary), SUMMARY_WEIGHT)
    return sorted(merged.values(), key=lambda h: -h.strength)
