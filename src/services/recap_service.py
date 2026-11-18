# Adapt the existing recap pipeline for bounded, request-scoped API calls.

from functools import partial
import logging
from pathlib import Path
from threading import BoundedSemaphore
from time import perf_counter
from typing import Any

from src.catalog.product_catalog import (
    build_catalog_plan, load_catalog, resolve_and_rank,
)
from src.catalog.product_groups import load_category_groups
from src.clients.image_generation import CurlImageClient
from src.clients.mwg_http import post_json_with_curl
from src.clients.product_translation import QWEN_API_URL, QwenProductTranslator
from src.core.config import Settings
from src.core.recap_config import RecapConfig
from src.imaging.background_templates import (
    GROUPS_PER_PAGE, require_backgrounds,
)
from src.imaging.image_files import stack_recap_pages
from src.imaging.product_cutout import background_session
from src.imaging.recap_layout import find_font
from src.services.recap_pipeline import generate_recap

logger = logging.getLogger(__name__)


class RecapBusyError(RuntimeError):
    """The process is already generating an image."""


class ProductSelectionError(ValueError):
    """Reject unresolved or unsupported codes before spending API calls."""

    def __init__(self, excluded: list[dict[str, str]]) -> None:
        super().__init__("Some product codes cannot be used for a recap")
        self.excluded = excluded


class RecapService:
    def __init__(
        self, config: RecapConfig, *,
        catalog: dict[str, dict[str, Any]],
        category_groups: dict[str, dict], output_dir: Path,
    ) -> None:
        self.config = config
        self.catalog = catalog
        self.category_groups = category_groups
        self.output_dir = output_dir
        self._capacity = BoundedSemaphore(1)

    @classmethod
    def from_settings(cls, settings: Settings) -> "RecapService":
        config = RecapConfig(
            api_key=settings.MWG_API_KEY.get_secret_value(),
            cookie=(settings.MWG_COOKIE.get_secret_value()
                    if settings.MWG_COOKIE else None),
            timeout=(15, settings.MWG_REQUEST_TIMEOUT_SECONDS),
            translation_workers=settings.MWG_TRANSLATION_WORKERS,
            image_workers=settings.MWG_IMAGE_WORKERS,
        )
        require_backgrounds(range(1, GROUPS_PER_PAGE + 1))
        find_font()
        background_session()
        return cls(
            config, catalog=load_catalog(settings.CATALOG_PATH),
            category_groups=load_category_groups(
                settings.CATEGORY_LABELS_PATH,
            ),
            output_dir=settings.OUTPUT_DIR,
        )

    def generate(self, productcodes: list[str]) -> Path:
        if not self._capacity.acquire(blocking=False):
            raise RecapBusyError("A recap is already being generated")
        try:
            return self._generate(productcodes)
        finally:
            self._capacity.release()

    def _generate(self, productcodes: list[str]) -> Path:
        started = perf_counter()
        _, excluded = resolve_and_rank(
            productcodes, self.catalog, category_groups=self.category_groups,
        )
        if excluded:
            raise ProductSelectionError(excluded)
        post_json = partial(
            post_json_with_curl, QWEN_API_URL,
            api_key=self.config.api_key, cookie=self.config.cookie,
            timeout=self.config.timeout,
        )
        # Cache translations only within this request; do not share user data.
        translator = QwenProductTranslator(post_json)
        plan = build_catalog_plan(
            productcodes, self.catalog, translate_product=translator.translate,
            category_groups=self.category_groups,
            translation_workers=self.config.translation_workers,
        )
        logger.info(
            "Recap planning/translation: %.2fs", perf_counter() - started,
        )
        first_page = generate_recap(
            CurlImageClient(self.config), plan, self.output_dir,
            image_workers=self.config.image_workers,
        )
        count = len(plan["categories"])
        page_count = (count + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE
        if page_count == 1:
            return first_page
        return stack_recap_pages([
            first_page.parent / f"recap_{index:02d}_final.png"
            for index in range(1, page_count + 1)
        ], first_page.parent / "recap_final.png")
