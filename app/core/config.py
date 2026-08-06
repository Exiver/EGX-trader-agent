"""
Centralized app settings, read from invironment variables(and .env locally ),

later phases add fields here (GEMINI API KEY, Database url, scraper target urls, ETC)
routs and services should alwas read config from here rather than calling os.env directly, so there is one scorce of thuth"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "local"
    log_level: str = "info"

    gemini_api_key: str = ""
    database_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()