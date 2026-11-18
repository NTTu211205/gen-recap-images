# Resolve shared resource locations from the project root, not the caller cwd.

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
CATALOG_PATH = PROJECT_DIR / "data" / "api_crawl_infor_new.json"
CATEGORY_LABELS_PATH = PROJECT_DIR / "data" / "category_labels.yaml"
OUTPUT_DIR = PROJECT_DIR / "output"
BACKGROUND_DIR = PROJECT_DIR / "background"
BACKGROUND_MODEL_PATH = PROJECT_DIR / "models" / "isnet-general-use.onnx"
