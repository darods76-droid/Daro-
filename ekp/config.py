"""Konfiguration - ausschliesslich ueber Umgebungsvariablen bzw. .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_ENV_LOADED = False


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimaler .env-Loader (kein externes Paket noetig)."""
    global _ENV_LOADED
    p = Path(path)
    if not p.is_file():
        _ENV_LOADED = True
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        # Bereits gesetzte echte Umgebungsvariablen haben Vorrang.
        os.environ.setdefault(key, value)
    _ENV_LOADED = True


def _env(name: str, default: str) -> str:
    if not _ENV_LOADED:
        load_dotenv()
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(_env(name, str(default))))
    except ValueError:
        return default


@dataclass
class Settings:
    """Laufzeit-Einstellungen der App."""

    calendar_provider: str = field(default_factory=lambda: _env("EKP_CALENDAR_PROVIDER", "demo"))
    te_key: str = field(default_factory=lambda: _env("EKP_TE_KEY", "guest:guest"))
    fmp_key: str = field(default_factory=lambda: _env("EKP_FMP_KEY", ""))

    news_provider: str = field(default_factory=lambda: _env("EKP_NEWS_PROVIDER", "rss"))
    newsapi_key: str = field(default_factory=lambda: _env("EKP_NEWSAPI_KEY", ""))

    lookahead_hours: int = field(default_factory=lambda: _env_int("EKP_LOOKAHEAD_HOURS", 72))
    news_lookback_hours: int = field(default_factory=lambda: _env_int("EKP_NEWS_LOOKBACK_HOURS", 96))
    min_importance: int = field(default_factory=lambda: _env_int("EKP_MIN_IMPORTANCE", 2))

    confirm_band: float = field(default_factory=lambda: _env_float("EKP_CONFIRM_BAND", 0.5))
    evidence_scale: float = field(default_factory=lambda: _env_float("EKP_EVIDENCE_SCALE", 3.0))
    news_half_life_hours: float = field(default_factory=lambda: _env_float("EKP_NEWS_HALF_LIFE", 36.0))

    db_path: str = field(default_factory=lambda: _env("EKP_DB", "data/ekp.sqlite3"))
    http_timeout: float = field(default_factory=lambda: _env_float("EKP_HTTP_TIMEOUT", 20.0))
    offline: bool = field(default_factory=lambda: _env("EKP_OFFLINE", "0") in ("1", "true", "yes"))


def get_settings() -> Settings:
    load_dotenv()
    return Settings()
