"""Duenner HTTP-Helfer auf Basis der Standardbibliothek."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = "ekp-wirtschaftskalender/1.0 (+https://github.com/)"


class FetchError(RuntimeError):
    """Netzwerk- oder Protokollfehler beim Abruf einer Quelle."""


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if bundle and os.path.isfile(bundle):
        ctx.load_verify_locations(bundle)
    return ctx


def get(url: str, timeout: float = 20.0, headers: dict[str, str] | None = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} bei {url}") from exc
    except Exception as exc:                                  # URLError, Timeout, SSL ...
        raise FetchError(f"Abruf fehlgeschlagen: {url} ({exc})") from exc


def get_json(url: str, timeout: float = 20.0, headers: dict[str, str] | None = None) -> Any:
    raw = get(url, timeout=timeout, headers={"Accept": "application/json", **(headers or {})})
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FetchError(f"Ungültiges JSON von {url}: {exc}") from exc
