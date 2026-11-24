# Adapt the existing recap pipeline for bounded, request-scoped API calls.

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
        config = RecapConfig.from_settings(settings)
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
        plan = build_catalog_plan(
            productcodes, self.catalog,
            category_groups=self.category_groups,
            image_size=self.config.image_size,
            steps=self.config.steps,
            cfg=self.config.cfg,
        )
        logger.info(
            "Recap planning: %.2fs", perf_counter() - started,
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
