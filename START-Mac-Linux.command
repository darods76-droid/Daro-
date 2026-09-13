#!/bin/sh
# DARO-CAD starten.
#
# macOS: doppelklicken. Meldet der Finder "nicht geprüfter Entwickler",
#        einmal mit Rechtsklick > Öffnen starten.
# Linux: doppelklicken oder im Terminal  ./START-Mac-Linux.command

cd "$(dirname "$0")" || exit 1

echo
echo "  ============================================"
echo "     DARO-CAD  -  Technische Zeichnungen"
echo "  ============================================"
echo

# Python 3.9 oder neuer suchen
PYCMD=""
for candidate in python3 python python3.13 python3.12 python3.11 python3.10 python3.9; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
            PYCMD="$candidate"
            break
        fi
    fi
done

if [ -z "$PYCMD" ]; then
    echo "  Python 3 wurde auf diesem Rechner nicht gefunden."
    echo
    echo "  So geht es weiter:"
    echo "    macOS : im Terminal   brew install python"
    echo "            oder von https://www.python.org/downloads/ laden"
    echo "    Ubuntu: im Terminal   sudo apt install python3"
    echo "    Fedora: im Terminal   sudo dnf install python3"
    echo
    echo "  Danach diese Datei erneut starten."
    echo
    printf "  Zum Schliessen Eingabetaste druecken. "
    read -r _
    exit 1
fi

if [ ! -f "daro_cad/__main__.py" ]; then
    echo "  Der Ordner \"daro_cad\" liegt nicht neben dieser Datei."
    echo
    echo "  Vermutlich wurde das ZIP nicht vollstaendig entpackt."
    echo "  Bitte entpacken und diese Datei aus dem entpackten Ordner starten."
    echo
    printf "  Zum Schliessen Eingabetaste druecken. "
    read -r _
    exit 1
fi

echo "  Python gefunden: $PYCMD ($("$PYCMD" -V 2>&1))"
echo
echo "  Der Browser oeffnet sich gleich von selbst."
echo "  Falls nicht, im Browser diese Adresse eingeben:"
echo
echo "       http://127.0.0.1:8765"
echo
echo "  Zum Beenden: Strg+C druecken oder dieses Fenster schliessen."
echo

"$PYCMD" -m daro_cad

echo
echo "  DARO-CAD wurde beendet."
printf "  Zum Schliessen Eingabetaste druecken. "
read -r _
