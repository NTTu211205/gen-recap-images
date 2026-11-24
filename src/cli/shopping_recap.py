# Run recap generation or export plans from the command line.

import argparse
import json
import logging
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

import requests
from dotenv import load_dotenv

from src.catalog.product_catalog import build_catalog_plan, load_catalog
from src.catalog.product_groups import load_category_groups
from src.clients.image_generation import CurlImageClient, MWGImageClient
from src.core.paths import CATALOG_PATH, CATEGORY_LABELS_PATH, OUTPUT_DIR
from src.core.recap_config import RecapConfig
from src.services.recap_pipeline import generate_recap

logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a MWG shopping recap",
    )
    parser.add_argument(
        "--plan", type=Path,
        help="Use an exported grouped generation plan instead of products",
    )
    parser.add_argument(
        "--export-plan", type=Path,
        help="Export without images",
    )
    parser.add_argument(
        "--read-timeout", type=float, default=120,
        help="curl total request timeout, or requests read timeout (seconds)",
    )
    parser.add_argument(
        "--transport", choices=("curl", "requests"), default="curl",
        help="HTTP transport (default: curl)",
    )
    parser.add_argument(
        "--catalog", type=Path,
        default=CATALOG_PATH,
        help="JSON source of product names/categories, indexed by productcode",
    )
    parser.add_argument(
        "--productcodes", nargs="+",
        help="Resolve these productcodes directly from the JSON catalog",
    )
    parser.add_argument(
        "--category-labels", type=Path, default=CATEGORY_LABELS_PATH,
        help="YAML mapping detailed catalog labels into recap display groups",
    )
    args = parser.parse_args()
    if bool(args.plan) == bool(args.productcodes):
        parser.error("Choose one input: --productcodes or --plan")
    if args.read_timeout <= 0:
        parser.error("--read-timeout must be greater than zero")
    return args


def main() -> None:
    args = parse_arguments()
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    if args.plan:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    else:
        plan = build_catalog_plan(
            args.productcodes, load_catalog(args.catalog),
            category_groups=load_category_groups(args.category_labels),
        )
    logger.info(
        "Plan: %s categories, %s requests, %s unresolved/excluded codes",
        len(plan.get("categories", [])), len(plan["requests"]),
        len(plan.get("excluded", [])),
    )
    if args.export_plan:
        args.export_plan.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"Plan exported: {args.export_plan}")
        return
    config = replace(
        RecapConfig.from_environment(),
        timeout=(15, args.read_timeout),
    )
    session_context = (
        requests.Session() if args.transport == "requests" else nullcontext()
    )
    with session_context as session:
        client = (
            CurlImageClient(config) if args.transport == "curl"
            else MWGImageClient(config, session)
        )
        try:
            final_path = generate_recap(
                client, plan, OUTPUT_DIR,
                image_workers=config.image_workers,
            )
        except requests.Timeout:
            logger.error(
                "API timed out; saved group assets are kept in output. "
                "No automatic retry was sent."
            )
            raise SystemExit(1) from None
    print(f"Image: {final_path.resolve()}")


if __name__ == "__main__":
    main()
