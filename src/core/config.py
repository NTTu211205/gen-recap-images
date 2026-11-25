# Read API settings without exposing MWG credentials in representations.

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core import paths


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=paths.PROJECT_DIR / ".env", env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "MWG Video Recap"
    APP_VERSION: str = "0.1.0"
    APP_DEBUG: bool = False
    MWG_API_KEY: SecretStr = SecretStr("")
    MWG_COOKIE: SecretStr | None = None
    API_URL: str = "https://ai.itmwg.vn/ai-mwg/qwen-edit-image/v1/images/edits"
    IMAGE_SIZE: str = "512x512"
    IMAGE_STEPS: int = 4
    IMAGE_CFG: float = 1.0
    IMAGE_WORKERS: int = Field(default=2, ge=1, le=8)
    MWG_REQUEST_TIMEOUT_SECONDS: float = Field(
        default=120, gt=0, le=600, allow_inf_nan=False,
    )
    CATALOG_PATH: Path = paths.CATALOG_PATH
    CATEGORY_LABELS_PATH: Path = paths.CATEGORY_LABELS_PATH
    OUTPUT_DIR: Path = paths.OUTPUT_DIR

    @property
    def MWG_IMAGE_WORKERS(self) -> int:
        return self.IMAGE_WORKERS


settings = Settings()
