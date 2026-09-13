# DARO-CAD

Eine CAD-App zum Anfertigen technischer Zeichnungen: 2D-Zeichenbrett im Browser,
Volumenkörper per Extrusion, normgerechte Ansichtsableitung mit verdeckten Kanten
und Export nach PDF, SVG und DXF. Mit installiertem **FreeCAD** kommen FCStd, STEP
und STL dazu.

## Drei Wege, die App zu benutzen

| Weg | Womit | Export |
|---|---|---|
| **Link anklicken** | nichts nötig, läuft sofort im Browser | PDF, SVG, DARO-CAD-Datei |
| **[DARO-CAD.html](DARO-CAD.html) doppelklicken** | eine Datei, kein Python | zusätzlich **DXF** |
| **`python3 -m daro_cad`** | Python 3.9+ | zusätzlich **FCStd, STEP, STL** (mit FreeCAD) |

Alle drei zeigen dieselbe App und rechnen gleich — die Ergebnisse stimmen
byteweise überein (siehe *Tests*). Sie unterscheiden sich nur darin, welche
Dateien sie herausgeben dürfen.

### Der schnellste Weg

Beim ersten Öffnen erscheint ein Startbildschirm mit drei Möglichkeiten:
**Beispiel ansehen** (eine fertige Zeichnung mit drei Ansichten), **Leeres Blatt**
oder **Kurz erklärt**. Später jederzeit über „Einstieg“ erreichbar.

Nach „Leeres Blatt“ ist das Linien-Werkzeug bereits gewählt — der erste Klick
zeichnet. Solange ein Werkzeug aktiv ist, steht der nächste erwartete Schritt
direkt am Mauszeiger und zusätzlich unten links.

### Auf Handy und Tablet

Die Oberfläche richtet sich nach der Bildschirmbreite, damit das Zeichenblatt
immer den Großteil des Platzes bekommt:

| Breite | Werkzeuge | Seitenleiste | Zeichenblatt |
|---|---|---|---|
| ab 1100 px | Leiste links | fest rechts | Rest |
| 700–1100 px | Leiste links | Schublade über „Mehr“ | Rest |
| unter 700 px | Leiste **unten**, wischbar | Schublade über „Mehr“ | **volle Breite** |

Gemessener Anteil der Zeichenfläche an der Fensterbreite: Handy hochkant 100 %,
Handy quer 86 %, Tablet 86 %, Laptop 71 %.

**Mit den Fingern:** ein Finger tippt Punkte und zieht Auswahlfenster, zwei Finger
schieben den Ausschnitt und zoomen. Während einer Zwei-Finger-Geste entsteht kein
Element.

Unten stehen die Grundformen zuerst: **Linie, Rechteck, Quadrat, Kreis, Bogen,
Text** — sechs davon gleichzeitig sichtbar, jede Fläche mindestens 44 × 44 px.
Der Rest folgt beim seitlichen Wischen.

### Die Datei-Fassung

`DARO-CAD.html` herunterladen und doppelklicken. Die ganze App steckt in dieser
einen Datei: kein Python, keine Installation, kein Server. Sie läuft auch ohne
Internet und kann als einzige Browser-Fassung **DXF** schreiben, weil örtliche
Downloads keiner Einschränkung unterliegen.

Wer die App über den Link geöffnet hat, kommt mit einem Klick auf
**„App speichern“** oben rechts an genau diese Datei.

> FCStd, STEP und STL fehlen in beiden Browser-Fassungen, denn dafür wird FreeCAD
> gebraucht. Diese Einträge sind im Export-Menü ausgegraut.

### Die Python-Fassung

```
python3 -m daro_cad
```

Mehr braucht es nicht — kein `pip install`, keine Fremdbibliotheken, nur Python 3.9
oder neuer. Der Browser öffnet sich von selbst auf <http://127.0.0.1:8765/>.

Wer kein Terminal mag, startet stattdessen per Doppelklick:

| System | Datei |
|---|---|
| Windows | `START-Windows.bat` |
| macOS, Linux | `START-Mac-Linux.command` |

Die Starter suchen Python selbst und sagen verständlich Bescheid, falls es fehlt.

Gegenüber der eigenständigen Datei kann diese Fassung zusätzlich: Zeichnungen in
einem Ordner ablegen statt im Browser-Speicher, FCStd/STEP/STL über FreeCAD
schreiben und FCStd/STEP einlesen.

---

## Was die App kann

**Zeichnen**
Linie, Polylinie (mit Bögen), Rechteck, Quadrat, Kreis, Bogen, Bogen über drei
Punkte, Ellipse, regelmäßiges Vieleck (3–64 Ecken), Punkt, Text und Schraffur.
Beim Rechteck erzwingt die Umschalttaste gleiche Seiten.
Objektfang auf Endpunkt, Mittelpunkt, Zentrum, Quadrant, Schnittpunkt, Lot und
Raster; Ortho- und Polarmodus; Auswahlfenster umschließend und kreuzend.

**Griffe**
Ein ausgewähltes Element zeigt seine Griffe; anfassen und ziehen ändert direkt
Endpunkt, Mittelpunkt, Radius, Achse oder Maßlage. Der Objektfang wirkt beim
Ziehen mit, und ein Zug ist genau ein Schritt im Rückgängig-Speicher.

**Ändern**
Verschieben, Kopieren, Drehen, Spiegeln, Skalieren, Versatz, Stutzen, Dehnen,
Runden, Fasen, Reihe (rechteckig und rund), Auflösen, Löschen — jeweils mit
unbegrenztem Rückgängig.

**Messen**
Abstand und Winkel zwischen zwei Punkten; Fläche und Umfang einer geschlossenen
Kontur, in mm² und cm².

**Bemaßen**
Längenmaß waagerecht/senkrecht/ausgerichtet, Winkelmaß, Radius- und
Durchmessermaß. Maßzahlen werden gerechnet, nicht getippt; wer will, überschreibt
sie im Eigenschaftenfeld. Enge Maße setzen die Pfeile automatisch nach außen,
kleine Bohrungen bekommen nur eine Hinweislinie.
Dazu **Toleranzen**: symmetrisch (±0,1), als Grenzmaße (oberes und unteres Abmaß
kleiner über- und untereinander) oder als ISO-Passung (H7, g6 …).

**Normgerechte Beschriftung**
Hinweislinie mit Pfeil, Knick und Auslauf; Oberflächenzeichen nach ISO 1302
(beliebig, spanend, spanlos, mit Rauheitswert); Form- und Lagetoleranzrahmen nach
ISO 1101 mit allen 14 Sinnbildern und bis zu drei Bezügen.

**Blöcke**
Eine Auswahl wird mit einem Basispunkt zum Block und danach beliebig oft
eingefügt — gedreht und skaliert; Halbmesser, Schrifthöhen und Schraffuren
wachsen mit. Mitgeliefert sind acht Symbole: Bohrung Ø10, Senkung 90°,
Sechskantschraube M8, Sechskantmutter M8, Passfeder A 8×7×25, Kehlnaht a4 nach
ISO 2553, Nordpfeil und Schnittpfeil. Ein Block lässt sich jederzeit wieder
auflösen; beim Export wird er in seine Elemente aufgelöst, damit er in jedem
Zielprogramm gleich aussieht.

**Blatt und Schriftfeld**
Blattformate A4 bis A0, Maßstäbe von 50:1 bis 1:1000, Zeichnungsrahmen mit
Heftrand und ein ausfüllbares Schriftfeld mit Projektionssymbol.

**3D und Ansichten**
Geschlossene Konturen lassen sich extrudieren — Innenkonturen werden zu
Bohrungen. Aus dem Körper leitet die App Vorderansicht, Draufsicht und
Seitenansicht ab und rechnet dabei aus, welche Kanten verdeckt sind: die kommen
strichliert auf den Layer „Verdeckt“. Volumen und Masse werden mitgeliefert.

**Austausch**
Import von DXF und den eigenen Zeichnungsdateien, Export nach PDF, SVG, DXF und
JSON. Mit FreeCAD zusätzlich FCStd, STEP und STL.

**KI-Helfer** *(nur in der Online-Fassung)*
Ein Reiter in der Seitenleiste nimmt eine Beschreibung entgegen — „Platte 120×80,
vier Bohrungen Ø9 im Raster 100×60" — und legt die Elemente an; daneben
beantwortet er Fragen zur Zeichnung und zur Norm.

Der Helfer bekommt **keine Rechte in der App**: was zurückkommt, ist eine
Datenliste, kein Programm. Nichts davon wird ausgeführt. Jedes Element wird Feld
für Feld geprüft — bekannte Art, endliche Zahlen innerhalb sinnvoller Grenzen,
bekannter Layer — und alles Unbekannte fällt weg; die App sagt dann, wie viele
Vorschläge sie aus welchem Grund verworfen hat. Eingefügtes ist ein einziger
Rückgängig-Schritt.

Fehlt die Fähigkeit — in der Datei-Fassung, oder ohne Einverständnis —,
verschwindet der Reiter und die App bleibt vollständig nutzbar.

---

## Bedienung

### Maus

| Aktion | Wirkung |
|---|---|
| Linke Taste | Punkt setzen bzw. auswählen |
| Rechte Taste oder `Enter` | Befehl abschließen |
| `Esc` | Befehl abbrechen |
| Mausrad | Zoomen an der Cursorposition |
| Mittlere Taste ziehen | Ansicht verschieben |
| Doppelklick | Alles zeigen |

Beim Auswahlfenster gilt die übliche CAD-Regel: von **links nach rechts** aufgezogen
werden nur vollständig umschlossene Elemente gefasst, von **rechts nach links** auch
angeschnittene.

### Koordinaten eingeben

Die Befehlszeile unten nimmt Zahlen genauso entgegen wie Befehle:

| Eingabe | Bedeutung |
|---|---|
| `100,50` | absolute Koordinate |
| `@50,0` | 50 mm nach rechts vom letzten Punkt |
| `@100<45` | 100 mm unter 45° vom letzten Punkt |
| `75` | 75 mm in Cursorrichtung |
| `kreis` | Werkzeug wechseln |

### Tasten

`L` Linie · `P` Polylinie · `R` Rechteck · `Q` Quadrat · `K` Kreis · `B` Bogen · `T` Text ·
`H` Schraffur · `M` Maß · `V` Verschieben · `C` Kopieren · `D` Drehen ·
`S` Stutzen · `E` Dehnen · `F` Runden · `Entf` Löschen · `Strg+A` alles wählen ·
`Strg+Z` / `Strg+Y` rückgängig / wiederholen · `Strg+S` speichern ·
`F1` Hilfe · `F3` Fang · `F7` Raster · `F8` Ortho · `F10` Polar

---

## Arbeitsablauf: von der Kontur zur fertigen Zeichnung

1. **Kontur zeichnen** — Außenumriss geschlossen, Bohrungen als Kreise darin.
2. **Alles auswählen** (`Strg+A`), Reiter *3D & Ansichten*, Höhe eintragen,
   **Auswahl extrudieren**. Volumen und Masse erscheinen sofort.
3. **Ansichten in die Zeichnung legen** — die App setzt Vorder-, Drauf- und
   Seitenansicht nach der eingestellten Projektionsmethode aufs Blatt und
   berechnet die verdeckten Kanten.
4. **Bemaßen und Schriftfeld füllen.**
5. **Export → PDF** für den Druck oder **DXF** für die Weiterverarbeitung.

Ein vollständiges Beispiel dafür steht in `examples/`:

```
python3 examples/erzeuge_beispiele.py
```

Das erzeugt `lagerplatte` (Platte mit zwei Bohrungen, drei Ansichten, Bemaßung)
und `winkelblech` (Schnittdarstellung mit Schraffur) — jeweils als
`.darocad.json`, `.pdf`, `.dxf` und `.svg`. Die JSON-Dateien lassen sich in der
App über *Öffnen* laden.

---

## FreeCAD anbinden

DARO-CAD läuft vollständig ohne FreeCAD. Ist FreeCAD vorhanden, schaltet die App
drei weitere Ausgabeformate frei und schreibt eine echte FreeCAD-Datei mit Skizze,
Volumenkörper und TechDraw-Blatt — dort lässt sich parametrisch weiterkonstruieren.

**Installieren**

| System | Befehl |
|---|---|
| Debian/Ubuntu | `sudo apt install freecad` |
| Fedora | `sudo dnf install freecad` |
| Arch | `sudo pacman -S freecad` |
| macOS | `brew install --cask freecad` |
| Windows | Installer von <https://www.freecad.org> |
| überall | AppImage, Snap (`snap install freecad`) oder Flatpak |

**Prüfen**

```
python3 -m daro_cad info
```

Meldet die App „FreeCAD: nicht gefunden“, obwohl FreeCAD installiert ist, dann
zeigen Sie ihr den Weg:

```
export FREECAD_CMD=/pfad/zu/freecadcmd        # Linux/macOS
setx FREECAD_CMD "C:\Program Files\FreeCAD\bin\FreeCADCmd.exe"   # Windows
```

Gesucht werden `freecadcmd`, `FreeCADCmd`, `freecad-cmd`, `freecad` und `FreeCAD`
im `PATH` sowie die üblichen Installationsorte. Bei AppImages zeigen Sie
`FREECAD_CMD` direkt auf die AppImage-Datei.

**Wie die Kopplung arbeitet**
DARO-CAD ruft FreeCAD als eigenständiges Programm auf (`freecadcmd`) und übergibt
die Zeichnung als JSON. Dadurch ist es gleichgültig, unter welcher Python-Version
FreeCAD installiert ist — Snap, Flatpak und AppImage funktionieren genauso wie ein
Systempaket. Der Kern selbst bleibt frei von Abhängigkeiten.

> **Ehrlicher Hinweis zum Prüfstand:** Der Container, in dem diese Version gebaut
> wurde, hat kein FreeCAD-Paket im Index — die Brücke konnte hier deshalb **nicht**
> gegen eine laufende FreeCAD-Installation getestet werden. Geprüft sind: die
> Erkennungslogik, die Fehlerpfade (verständliche Meldung statt Absturz, alle
> FreeCAD-Formate bleiben in der Oberfläche ausgegraut) und die Syntax der beiden
> Skripte, die in FreeCAD laufen. Bitte nach der Installation einmal
> `python3 -m daro_cad info` und einen FCStd-Export ausprobieren; wenn etwas hakt,
> steht die vollständige FreeCAD-Ausgabe in der Fehlermeldung.

---

## Aufbau

```
daro_cad/           Python-Kern, nur Standardbibliothek
  geom.py           Vektorrechnung, Bögen, Schnittpunkte
  model.py          Dokument, Layer, Blattformate, Entitäten
  primitives.py     Bemaßung, Schraffur, Rahmen, Schriftfeld
  svg_export.py     SVG in exakter Blattgröße
  pdf_export.py     Vektor-PDF (eigener Writer, Helvetica-Metriken)
  dxf.py            DXF R12 schreiben und lesen
  solid.py          Extrusion von Profilen zu Prismen
  views.py          Ansichtsableitung mit Verdeckt-Kanten-Berechnung
  freecad_bridge.py optionale Kopplung an FreeCAD
  server.py         lokaler HTTP-Dienst und JSON-API
web/                Zeichen-App (ES-Module, kein Framework)
  js/geom.js        Spiegel von geom.py
  js/prims.js       Spiegel von primitives.py
  js/doc.js         Dokument, Layer, Rückgängig
  js/render.js      Canvas-Ausgabe
  js/snap.js        Objektfang
  js/tools.js       Werkzeuge und Befehlsablauf
  js/modify.js      Stutzen, Runden, Versatz und die übrigen Änderungen
  js/grips.js       Griffe treffen und ziehen
  js/blocks.js      mitgelieferte Symbolbibliothek
  js/ai.js          KI-Helfer samt Prüfung jeder Antwort
  js/view3d.js      3D-Vorschau
  js/solid.js       Spiegel von solid.py
  js/views.js       Spiegel von views.py
  js/export-*.js    Spiegel von svg_export.py, dxf.py, pdf_export.py
  js/import-dxf.js  DXF einlesen ohne Server
  js/api.js         spricht den Python-Dienst an
  js/api-local.js   rechnet alles im Browser (eigenständige Fassung)
  js/app.js         Zusammenspiel und Oberfläche
build_standalone.py bündelt web/ zu DARO-CAD.html
START-*.bat/.command  Starter zum Doppelklicken
tests/              79 Tests für Kern und Browser-Fassung
examples/           Beispielzeichnungen samt Erzeugungsskript
```

**Warum manches doppelt vorkommt.** `primitives.py` und `prims.js` berechnen
dasselbe, ebenso `solid.py`/`solid.js`, `views.py`/`views.js` und die drei
Exporter. Das ist Absicht und hat zwei Gründe: Die Bemaßung auf dem Bildschirm
muss dem entsprechen, was später im PDF steht — ein Server-Rundlauf pro
Mausbewegung wäre dafür zu träge. Und nur so kommt die eigenständige HTML-Datei
ganz ohne Python aus.

Damit die beiden Seiten nicht auseinanderlaufen, vergleicht die Testsuite sie
gegeneinander: `tests/test_web_parity.py` lässt dieselbe Zeichnung von Python und
von Node.js exportieren und besteht nur, wenn SVG, DXF und PDF **byteweise
gleich** sind. Ebenso werden Extrusion, jede einzelne projizierte Kante und der
DXF-Import verglichen. Eine Abweichung von 0,1 mm an einer Pfeilspitze lässt die
Tests fehlschlagen.

**Die eigenständige Datei neu bauen:**

```
python3 build_standalone.py
```

Browser laden über `file://` keine einzelnen ES-Module nach; das Skript kapselt
deshalb jedes Modul in eine Funktion und schreibt alles zusammen mit CSS und
HTML in `DARO-CAD.html`.

### Zeichnungsformat

Eine Zeichnung ist schlichtes JSON — lesbar, versionierbar, skriptbar:

```json
{
  "version": 1,
  "meta": { "title": "Lagerplatte", "scale": "1:1", "sheet": "A3" },
  "layers": [ { "name": "Kontur", "color": "#111111", "lineweight": 0.5 } ],
  "entities": [
    { "type": "line", "layer": "Kontur", "a": [0, 0], "b": [120, 0] },
    { "type": "circle", "layer": "Kontur", "c": [30, 35], "r": 12 },
    { "type": "dim", "kind": "linear", "p1": [0, 0], "p2": [120, 0], "pos": [60, -20] },
    { "type": "insert", "layer": "Kontur", "name": "Schraube M8 (SK)",
      "p": [30, 35], "rot": 0, "scale": 1 }
  ],
  "blocks": {
    "Schraube M8 (SK)": {
      "base": [0, 0],
      "entities": [ { "type": "circle", "layer": "Kontur", "c": [0, 0], "r": 4 } ]
    }
  }
}
```

Koordinaten sind Millimeter, die Y-Achse zeigt nach oben, Winkel laufen in Grad
gegen den Uhrzeigersinn — dieselbe Konvention wie in DXF.

Ein `insert` verweist auf einen Block: dessen `base` landet auf `p`, alles
Weitere wird gedreht und skaliert. Beim Export wird der Verweis aufgelöst, damit
die Zeichnung in jedem Zielprogramm gleich aussieht.

### Ohne Oberfläche arbeiten

```
python3 -m daro_cad export zeichnung.darocad.json zeichnung.pdf
python3 -m daro_cad export fremd.dxf umgewandelt.svg
python3 -m daro_cad info
python3 -m daro_cad --port 9000 --no-browser --workspace ~/Zeichnungen
```

---

## Normbezug

Die Voreinstellungen folgen den einschlägigen Normen:

* **DIN EN ISO 5457** — Blattformate, Zeichnungsrahmen, Heftrand
* **DIN EN ISO 7200** — Datenfelder im Schriftfeld
* **DIN ISO 128-20** — Linienarten und Liniengruppe 0,5 (breit 0,5 mm / schmal 0,25 mm)
* **DIN ISO 128-24** — verdeckte Kanten als Strichlinie; deckungsgleiche Kanten
  werden sichtbar gezeichnet
* **DIN ISO 128-30/34** — Projektionsmethode 1 (Europa), umschaltbar auf Methode 3
* **DIN ISO 129-1** — Maßpfeile, Maßhilfslinien, Lage der Maßzahl
* **DIN ISO 5455** — Maßstäbe
* **ISO 2768** — voreingestellte Allgemeintoleranz
* **ISO 286** — Grundtoleranzgrade der Passungen (H7, g6 …)
* **ISO 1302** — Oberflächenangaben
* **ISO 1101** — Form- und Lagetoleranzen, 14 Sinnbilder
* **ISO 2553** — Schweißsinnbilder (Kehlnaht im mitgelieferten Symbolvorrat)
* **DIN EN ISO 4014 / 4032, DIN 6885** — Maße der mitgelieferten Symbole
  (Sechskant SW13 für M8, Passfeder Form A)

Maßzahlen verwenden das Komma als Dezimaltrennzeichen; im Schriftfeld lässt sich
das umstellen.

---

## Grenzen

Klar benannt, damit niemand davon überrascht wird:

* **Keine booleschen Operationen.** Bohrungen und Ausschnitte entstehen über
  Innenkonturen im Profil, nicht durch Abziehen von Körpern. Für abgesetzte
  Bauteile die Ansichten aus mehreren Extrusionen zusammensetzen — oder das Modell
  über die FreeCAD-Brücke weiterbearbeiten.
* **Extrusion nur entlang Z**, also senkrecht zur Zeichenebene. Rotationskörper
  und Züge entlang eines Pfads gibt es nicht.
* **Runden und Fasen brauchen Linien.** Ein Rechteck ist eine Polylinie — vorher
  *Auflösen* anwenden.
* **Layernamen bleiben ASCII** (`Bemassung` statt `Bemaßung`). Umlaute in
  Layernamen bereiten beim DXF-Austausch mit anderen Programmen Ärger; die
  Oberfläche selbst ist durchgehend deutsch beschriftet.
* **Bemaßungen werden beim DXF-Export aufgelöst** in Linien, Pfeile und Text. Sie
  sehen dadurch in jedem Zielprogramm gleich aus, sind dort aber nicht mehr
  assoziativ.
* **Kreise werden für die 3D-Ableitung angenähert** (48 Kanten). Auf die
  Ansichten wirkt sich das nicht sichtbar aus, auf berechnete Volumen mit
  weniger als 0,1 % Abweichung.
* **Blöcke werden beim Export aufgelöst**, nicht als DXF-`INSERT` geschrieben.
  In der Zeichnung selbst bleibt der Block ein Element: ändert man seinen Inhalt,
  ändern sich alle Verweise mit.
* **Blockmaßstab ist gleichmäßig** — ein Block lässt sich nicht in X anders
  strecken als in Y. Beim Verschachteln ist bei acht Ebenen Schluss, damit ein
  Block, der sich selbst enthält, die App nicht aufhängt.
* **Der KI-Helfer braucht die Online-Fassung.** In der Datei-Fassung fehlt ihm
  die Schnittstelle, und der Reiter erscheint erst gar nicht.

---

## Tests

```
python3 tests/test_daro_cad.py
python3 tests/test_web_parity.py
```

79 Tests decken Geometrie, Dokumentformat, Bemaßung samt Toleranzen, Ellipse,
Hinweislinie, Oberflächen- und Form-/Lagezeichen, Blöcke, Schriftfeld, alle drei
Exporter samt DXF-Rundlauf, Extrusion, Ansichtsableitung, die HTTP-API und die
Fehlerpfade der FreeCAD-Brücke ab — dazu die byteweise Übereinstimmung zwischen
Python-Kern und Browser-Fassung. Die Vergleichstests brauchen Node.js; fehlt es,
werden sie übersprungen statt zu scheitern.

Zwei Tests halten Bildschirm und Papier zusammen: Für **jede** Entitätsart wird
geprüft, dass der Renderer sie zeichnet *und* der Exportweg Zeichenelemente
liefert. Genau daran fehlte es einmal — Ellipse, Hinweislinie, Oberflächen- und
Form-/Lagezeichen standen im PDF, blieben am Bildschirm aber unsichtbar.

Die Zeichen-App selbst wurde mit Playwright im Browser durchgefahren: Zeichnen mit
Maus und Tastatur, Griffe ziehen, jedes neue Werkzeug einmal bedienen, Blöcke
erstellen/einfügen/auflösen samt Rückgängig, Auswahl, Runden, Stutzen, Dehnen,
Schraffur, Extrusion, Ansichtsableitung, Zwei-Finger-Gesten auf Handygröße, der
KI-Helfer mit nachgebildeter Schnittstelle (gültige Antworten kommen an,
ungültige werden abgewiesen) und alle Exportwege — ohne Konsolenfehler.

---

## Lizenz

MIT.
