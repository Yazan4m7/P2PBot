from __future__ import annotations

from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SimulatorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="P2PSIM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/p2psim.sqlite3"
    seed: int = 424242
    default_asset: str = "USDT"
    default_fiat: str = "JOD"
    initial_reference_price: float = Field(default=0.7090, gt=0)
    payment_timeout_seconds: int = Field(default=15 * 60, ge=30)
    default_speed: float = Field(default=1.0, ge=0.0, le=1000.0)
    frontend_origin: str = "http://127.0.0.1:5173"
    auth_required: bool = True
    test_api_key: str = "SIMULATOR_TEST_KEY"
    test_api_secret: str = "SIMULATOR_TEST_SECRET"
    scheduler_lease_seconds: int = Field(default=30, ge=5, le=300)
    simulator_mode: bool = True

    @field_validator("default_asset", "default_fiat")
    @classmethod
    def uppercase(cls, value: str) -> str:
        return value.strip().upper()


@lru_cache(maxsize=1)
def get_settings() -> SimulatorSettings:
    return SimulatorSettings()
