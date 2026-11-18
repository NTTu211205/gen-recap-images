# Remove opaque product backgrounds locally and keep reusable RGBA PNG cutouts.

import logging
import math
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from src.core.paths import BACKGROUND_MODEL_PATH

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def background_session():
    """Load explicit ONNX weights once in memory, without downloading."""
    model_path = Path(
        os.getenv("REMBG_MODEL_PATH", str(BACKGROUND_MODEL_PATH)),
    ).expanduser().resolve()
    if not model_path.is_file():
        raise FileNotFoundError(
            f"Background-removal model not found: {model_path}. "
            "Provide the ONNX file or set REMBG_MODEL_PATH."
        )
    from rembg import new_session

    # rembg validates custom paths against this directory; dis_custom loads
    # the supplied file directly and never invokes the model downloader.
    os.environ["U2NET_HOME"] = str(model_path.parent)
    logger.info("Loading background-removal model: %s", model_path)
    return new_session(
        "dis_custom", model_path=str(model_path),
        providers=["CPUExecutionProvider"],
    )


def has_transparency(image: Image.Image) -> bool:
    low, high = image.convert("RGBA").getchannel("A").getextrema()
    return low < 250 and high > 0


def restore_solid_interiors(
    source: Image.Image, cutout: Image.Image,
) -> Image.Image:
    """Restore solid faces, including low-confidence grille textures."""
    if source.size != cutout.size:
        raise ValueError("Cutout size must match its source image")
    alpha = cutout.getchannel("A")
    # Grilles can retain only faint alpha and connect to the exterior, so
    # filling holes at 128 alone leaves large parts of the device see-through.
    exterior = alpha.point(lambda value: 255 if value >= 16 else 0)
    width, height = exterior.size
    border = (
        [(x, 0) for x in range(width)]
        + [(x, height - 1) for x in range(width)]
        + [(0, y) for y in range(height)]
        + [(width - 1, y) for y in range(height)]
    )
    for point in border:
        if exterior.getpixel(point) == 0:
            ImageDraw.floodfill(exterior, point, 128)
    interior = exterior.point(lambda value: 0 if value == 128 else 255)
    # Keep the original soft silhouette rather than hardening its outer edge.
    interior = interior.filter(ImageFilter.MinFilter(3))
    result = Image.composite(source.convert("RGBA"), cutout, interior)
    result.putalpha(ImageChops.lighter(alpha, interior))
    return result


def remove_product_background(
    source: Image.Image, *, preserve_interior: bool = False,
) -> Image.Image:
    """Keep real transparency; segment opaque images without color keying."""
    image = source.convert("RGBA")
    if image.getchannel("A").getextrema()[1] == 0:
        raise ValueError("Product image is completely transparent")
    if has_transparency(image):
        return image
    from rembg import remove

    logger.info("Removing product background locally")
    result = remove(image, session=background_session())
    if not isinstance(result, Image.Image):
        raise ValueError("Background removal did not return an image")
    result = result.convert("RGBA")
    if preserve_interior:
        result = restore_solid_interiors(image, result)
    if not has_transparency(result):
        raise ValueError("Background removal did not produce a usable cutout")
    return result


def save_product_cutout(
    path: Path, *, preserve_interior: bool = False,
) -> Path:
    """Preserve the original asset and cache its transparent PNG beside it."""
    suffix = "_solid_v2_cutout.png" if preserve_interior else "_cutout.png"
    output = path.with_name(f"{path.stem}{suffix}")
    if (
        output.exists()
        and output.stat().st_mtime_ns >= path.stat().st_mtime_ns
    ):
        with Image.open(output) as cached:
            if has_transparency(cached):
                return output
    with Image.open(path) as source:
        if path.suffix.lower() == ".png" and has_transparency(source):
            return path
        cutout = remove_product_background(
            source, preserve_interior=preserve_interior,
        )
        cutout.save(output, format="PNG")
    logger.info("Transparent product cutout saved: %s", output)
    return output


def _load_cluster_products(paths: list[Path]) -> list[Image.Image]:
    products = []
    for path in paths:
        with Image.open(path) as source:
            cutout = source.convert("RGBA")
        bounds = cutout.getchannel("A").point(
            lambda value: 255 if value > 16 else 0,
        ).getbbox()
        if bounds is None or not has_transparency(cutout):
            raise ValueError(f"Invalid transparent cutout: {path.name}")
        products.append(cutout.crop(bounds))
    return products


def _compose_cluster_row(products: list[Image.Image]) -> Image.Image:
    """Place a tall hero behind its companions on a shared ground plane."""
    thumbnails = [
        ImageOps.contain(product, (580, 760), Image.Resampling.LANCZOS)
        for product in products
    ]
    # Tall objects sit behind lower objects rather than floating above them.
    thumbnails.sort(key=lambda image: image.height, reverse=True)
    hero = thumbnails[0]
    order = [hero]
    for index, product in enumerate(thumbnails[1:], 1):
        product = product.resize(
            (max(1, round(product.width * 0.88)),
             max(1, round(product.height * 0.88))),
            Image.Resampling.LANCZOS,
        )
        if index % 2:
            order.insert(0, product)
        else:
            order.append(product)
    positions = []
    x = 20
    baseline = hero.height + 24
    for index, product in enumerate(order):
        bottom = baseline - 20 if product is hero else baseline
        positions.append((product, x, bottom - product.height))
        x += product.width
        if index + 1 < len(order):
            x -= round(min(product.width, order[index + 1].width) * 0.22)
    size = (x + 20, baseline + 24)
    shadow = Image.new("RGBA", size)
    draw = ImageDraw.Draw(shadow)
    for product, left, top in positions:
        bottom = top + product.height
        inset = round(product.width * 0.12)
        draw.ellipse(
            (left + inset, bottom - 8,
             left + product.width - inset, bottom + 10),
            fill=(25, 20, 65, 65),
        )
    row = shadow.filter(ImageFilter.GaussianBlur(8))
    # Draw the rear hero first so foreground objects overlap it slightly.
    for product, left, top in sorted(
        positions, key=lambda item: item[0] is not hero,
    ):
        row.alpha_composite(product, (left, top))
    return row


def merge_product_cutouts(paths: list[Path], output: Path) -> Path:
    """Keep every product in a compact, layered display without grid cells."""
    if not paths:
        raise ValueError("No product cutouts to merge")
    if len(paths) == 1:
        return paths[0]
    products = _load_cluster_products(paths)
    columns = 3 if len(products) <= 6 else 4
    row_count = math.ceil(len(products) / columns)
    per_row, extra = divmod(len(products), row_count)
    rows = []
    offset = 0
    for index in range(row_count):
        count = per_row + (index < extra)
        row = _compose_cluster_row(products[offset:offset + count])
        rows.append(ImageOps.contain(
            row, (984, 984), Image.Resampling.LANCZOS,
        ))
        offset += count
    tops = [0]
    for rear, front in zip(rows, rows[1:]):
        overlap = round(min(rear.height, front.height) * 0.22)
        tops.append(tops[-1] + rear.height - overlap)
    cluster = Image.new("RGBA", (1024, tops[-1] + rows[-1].height))
    for top, row in zip(tops, rows):
        cluster.alpha_composite(row, ((1024 - row.width) // 2, top))
    thumbnail = ImageOps.contain(
        cluster, (984, 984), Image.Resampling.LANCZOS,
    )
    image = Image.new("RGBA", (1024, 1024))
    image.alpha_composite(thumbnail, (
        (1024 - thumbnail.width) // 2, 1004 - thumbnail.height,
    ))
    image.save(output, format="PNG")
    return output
