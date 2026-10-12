from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(val: str) -> list[str]:
    return [s.strip() for s in val.split(",") if s.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # France Travail
    france_travail_client_id: str = ""
    france_travail_client_secret: str = ""

    # Adzuna
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "fr"

    # RSS (comma-separated URLs)
    rss_feed_urls: str = ""

    # Filters (comma-separated values)
    target_sectors: str = ""
    target_location: str = ""
    target_contract_types: str = ""
    target_seniority: str = ""

    # Scoring
    openai_api_key: str = ""
    scoring_model: str = "gpt-4o-mini"
    scoring_threshold: int = 7
    target_profile: str = "Backend Python developer, 3 years experience"

    # Notifications
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://jobbot:jobbot@localhost:5432/jobbot"

    # Web application
    webapp_secret: str = ""
    webapp_port: int = 8080

    # Geocoding (Nominatim)
    nominatim_user_agent: str = ""
    geocode_interval: int = 10  # minutes

    # Scheduler intervals (minutes)
    fetch_france_travail_interval: int = 120
    fetch_rss_interval: int = 30
    fetch_adzuna_interval: int = 60
    score_and_notify_interval: int = 5

    # Parsed lists (populated by model_validator)
    sectors_list: list[str] = []
    contract_types_list: list[str] = []
    seniority_list: list[str] = []
    feed_urls_list: list[str] = []

    @model_validator(mode="after")
    def _parse_csv_fields(self) -> Settings:
        self.sectors_list = _split_csv(self.target_sectors)
        self.contract_types_list = _split_csv(self.target_contract_types)
        self.seniority_list = _split_csv(self.target_seniority)
        self.feed_urls_list = _split_csv(self.rss_feed_urls)
        return self

    @property
    def france_travail_enabled(self) -> bool:
        return bool(self.france_travail_client_id and self.france_travail_client_secret)

    @property
    def adzuna_enabled(self) -> bool:
        return bool(self.adzuna_app_id and self.adzuna_app_key)

    @property
    def rss_enabled(self) -> bool:
        return bool(self.feed_urls_list)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_webhook_url)

    @property
    def scoring_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def geocoding_enabled(self) -> bool:
        return bool(self.nominatim_user_agent)

    @property
    def webapp_enabled(self) -> bool:
        return bool(self.webapp_secret)


settings = Settings()
