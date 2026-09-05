"""Konfiguration. Wird aus Umgebungsvariablen bzw. einer .env-Datei gelesen."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
DATA_DIR = ROOT / "data"


def _load_dotenv(path: Path) -> None:
    """Minimaler .env-Reader – vorhandene Umgebungsvariablen haben Vorrang."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")


def _env(key: str, default: str) -> str:
    value = os.environ.get(key, "").strip()
    return value if value else default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(float(_env(key, str(default))))
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    value = _env(key, "1" if default else "0").lower()
    return value in ("1", "true", "yes", "ja", "on")


def _env_list(key: str, default: str) -> list[str]:
    return [item.strip().upper() for item in _env(key, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    provider: str = _env("FW_PROVIDER", "auto")
    twelvedata_key: str = _env("FW_TWELVEDATA_KEY", "")

    # Capital.com – bevorzugte Quelle, sobald die drei Angaben vorliegen
    capital_api_key: str = _env("FW_CAPITAL_API_KEY", "")
    capital_identifier: str = _env("FW_CAPITAL_IDENTIFIER", "")
    capital_password: str = _env("FW_CAPITAL_PASSWORD", "")
    capital_demo: bool = _env_bool("FW_CAPITAL_DEMO", True)

    pairs: list[str] = field(
        default_factory=lambda: _env_list(
            "FW_PAIRS",
            "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD,NZDUSD,EURJPY,EURGBP,GBPJPY",
        )
    )
    timeframes: list[str] = field(
        default_factory=lambda: [tf.lower() for tf in _env_list("FW_TIMEFRAMES", "15m,1h,4h,1d")]
    )

    scan_interval: int = _env_int("FW_SCAN_INTERVAL", 60)
    arm_threshold: float = _env_float("FW_ARM_THRESHOLD", 62.0)

    host: str = _env("FW_HOST", "127.0.0.1")
    port: int = _env_int("FW_PORT", 8000)

    webhook_url: str = _env("FW_WEBHOOK_URL", "")
    telegram_token: str = _env("FW_TELEGRAM_TOKEN", "")
    telegram_chat_id: str = _env("FW_TELEGRAM_CHAT_ID", "")

    account_balance: float = _env_float("FW_ACCOUNT_BALANCE", 10_000.0)
    account_currency: str = _env("FW_ACCOUNT_CURRENCY", "EUR").upper()
    risk_percent: float = _env_float("FW_RISK_PERCENT", 1.0)

    db_path: Path = DATA_DIR / "forexwatch.db"

    @property
    def capital_ready(self) -> bool:
        """Liegen alle drei Angaben fuer Capital.com vor?"""
        return bool(self.capital_api_key and self.capital_identifier and self.capital_password)

    @property
    def execution_timeframe(self) -> str:
        """Der Timeframe, auf dem Ein- und Ausstiege berechnet werden."""
        return self.timeframes[0] if self.timeframes else "1h"


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
