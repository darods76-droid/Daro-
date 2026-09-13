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
oder **Kurz erklärt**. Später jederzeit über „Einstieg“ oben rechts erreichbar.

Solange ein Werkzeug aktiv ist, steht der nächste erwartete Schritt direkt am
Mauszeiger — und zusätzlich unten links.

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
Linie, Polylinie (mit Bögen), Rechteck, Kreis, Bogen, Punkt, Text und Schraffur.
Objektfang auf Endpunkt, Mittelpunkt, Zentrum, Quadrant, Schnittpunkt, Lot und
Raster; Ortho- und Polarmodus; Auswahlfenster umschließend und kreuzend.

**Ändern**
Verschieben, Kopieren, Drehen, Spiegeln, Skalieren, Versatz, Stutzen, Dehnen,
Runden, Fasen, Auflösen, Löschen — jeweils mit unbegrenztem Rückgängig.

**Bemaßen**
Längenmaß waagerecht/senkrecht/ausgerichtet, Winkelmaß, Radius- und
Durchmessermaß. Maßzahlen werden gerechnet, nicht getippt; wer will, überschreibt
sie im Eigenschaftenfeld. Enge Maße setzen die Pfeile automatisch nach außen,
kleine Bohrungen bekommen nur eine Hinweislinie.

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

`L` Linie · `P` Polylinie · `R` Rechteck · `K` Kreis · `B` Bogen · `T` Text ·
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
tests/              60 Tests für Kern und Browser-Fassung
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
    { "type": "dim", "kind": "linear", "p1": [0, 0], "p2": [120, 0], "pos": [60, -20] }
  ]
}
```

Koordinaten sind Millimeter, die Y-Achse zeigt nach oben, Winkel laufen in Grad
gegen den Uhrzeigersinn — dieselbe Konvention wie in DXF.

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

---

## Tests

```
python3 -m unittest discover -s tests -v
```

60 Tests decken Geometrie, Dokumentformat, Bemaßung, Schriftfeld, alle drei
Exporter samt DXF-Rundlauf, Extrusion, Ansichtsableitung, die HTTP-API und die
Fehlerpfade der FreeCAD-Brücke ab — dazu die byteweise Übereinstimmung zwischen
Python-Kern und Browser-Fassung. Die Vergleichstests brauchen Node.js; fehlt es,
werden sie übersprungen statt zu scheitern.

Die Zeichen-App selbst wurde mit Playwright im Browser durchgefahren: Zeichnen mit
Maus und Tastatur, Auswahl, Auflösen, Runden, Stutzen, Dehnen, Schraffur,
Verschieben, Extrusion, Ansichtsableitung und alle Exportwege — ohne
Konsolenfehler.

---

## Lizenz

MIT.
