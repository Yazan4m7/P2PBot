from __future__ import annotations

from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    binance_mgs_base: str = "https://www.binance.com"
    database_url: str = "sqlite:///./data/p2pbot.sqlite3"
    default_fiat: str = "JOD"
    default_asset: str = "USDT"
    scan_limit: int = Field(default=20, ge=1, le=20)
    scan_interval_seconds: float = Field(default=10.0, ge=2.0)
    request_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)

    min_completion_rate: float = Field(default=95.0, ge=0.0, le=100.0)
    min_merchant_orders: int = Field(default=20, ge=0)
    min_net_roi_pct: float = Field(default=0.20)
    max_trade_fiat: float = Field(default=500.0, gt=0)
    slippage_bps_per_leg: float = Field(default=5.0, ge=0)
    platform_fee_bps_per_leg: float = Field(default=0.0, ge=0)
    fixed_bank_fee_buy: float = Field(default=0.0, ge=0)
    fixed_bank_fee_sell: float = Field(default=0.0, ge=0)
    preferred_payment_methods: list[str] = Field(default_factory=list)

    @field_validator("default_fiat", "default_asset")
    @classmethod
    def uppercase_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("preferred_payment_methods", mode="before")
    @classmethod
    def parse_payment_methods(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [part.strip().upper() for part in value.split(",") if part.strip()]
        return [str(part).strip().upper() for part in value if str(part).strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
