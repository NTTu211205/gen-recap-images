# Configure MWG clients independently of API settings.

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RecapConfig:
    """Configuration passed explicitly to the API client."""

    api_key: str = field(repr=False)
    cookie: str | None = field(default=None, repr=False)
    api_url: str = (
        "https://ai.itmwg.vn/ai-mwg/qwen-edit-image/v1/images/edits"
    )
    model: str = "MWG"
    image_size: str = "512x512"
    steps: int = 8
    cfg: float = 1.0
    timeout: tuple[float, float] = (15, 300)
    image_workers: int = 2

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("Missing MWG_API_KEY environment variable")
        if not 1 <= self.image_workers <= 8:
            raise ValueError("Worker counts must be between 1 and 8")

    @classmethod
    def from_settings(cls, settings: Any) -> "RecapConfig":
        return cls(
            api_key=settings.MWG_API_KEY.get_secret_value(),
            cookie=(settings.MWG_COOKIE.get_secret_value()
                    if settings.MWG_COOKIE else None),
            api_url=settings.API_URL,
            image_size=settings.IMAGE_SIZE,
            steps=settings.IMAGE_STEPS,
            cfg=settings.IMAGE_CFG,
            timeout=(15, settings.MWG_REQUEST_TIMEOUT_SECONDS),
            image_workers=settings.IMAGE_WORKERS,
        )

    @classmethod
    def from_environment(cls) -> "RecapConfig":
        from src.core.config import Settings
        return cls.from_settings(Settings())
