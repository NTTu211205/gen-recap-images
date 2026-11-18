# Configure MWG clients independently of API settings.

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecapConfig:
    """Configuration passed explicitly to the API client."""

    api_key: str = field(repr=False)
    cookie: str | None = field(default=None, repr=False)
    api_url: str = (
        "https://ai.itmwg.vn/ai-mwg/gen-image/v1/images/generations"
    )
    model: str = "MWG"
    translate: bool = False
    image_size: str = "1024x1024"
    timeout: tuple[float, float] = (15, 300)
    translation_workers: int = 4
    image_workers: int = 2

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("Missing MWG_API_KEY environment variable")
        for workers in (self.translation_workers, self.image_workers):
            if not 1 <= workers <= 8:
                raise ValueError("Worker counts must be between 1 and 8")

    @classmethod
    def from_environment(cls) -> "RecapConfig":
        return cls(
            api_key=os.getenv("MWG_API_KEY", ""),
            cookie=os.getenv("MWG_COOKIE"),
            translation_workers=int(os.getenv("MWG_TRANSLATION_WORKERS", "4")),
            image_workers=int(os.getenv("MWG_IMAGE_WORKERS", "2")),
        )
