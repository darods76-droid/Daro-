#!/usr/bin/env bash
# Startet die Weboberfläche. Ohne Argumente: Port 8000.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m ekp serve "$@"
