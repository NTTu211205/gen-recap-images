#!/usr/bin/env bash
# Resolve supplied productcodes from data/api_crawl_infor_new.json at runtime.
# Export a draft with ranked selections awaiting Qwen (no API calls):
# bash gen_images.sh --productcodes 0160016000111 --export-plan data/plan.json
# Export ready image payloads: add --translate-products to --export-plan.
# Generation translates selected names with Qwen automatically.
# Generate images: bash gen_images.sh --productcodes 0160016000111 0164219000082
# Credentials are loaded from .env by Python; never embedded in this file.
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
uv run --project "$PROJECT_DIR" python -m src.cli.shopping_recap "$@"
