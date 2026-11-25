# Short product-photo prompts for image editing and generation.

from typing import Any

PRODUCT_PHOTO_STYLE = (
    "Photorealistic studio product photograph. One view of each object. "
    "Plain white background, soft even lighting, realistic materials. "
    "The products fill most of the frame with a small clear margin."
)

QWEN_EDIT_IMAGE_PROMPT_TEMPLATE = (
    "Identify and isolate only the main {product_type} product in the "
    "provided image. Preserve the {product_type} exactly as it appears in the "
    "original image, including its shape, proportions, colors, materials, "
    "surface details, logos, labels, text, screens, displays, packaging "
    "details, attached accessories, and all visible components. Any image, "
    "text, graphic, reflection, interface, or content displayed on or "
    "printed directly on the {product_type} must remain part of the product "
    "and must not be treated as a separate object. Remove everything that is "
    "not part of the {product_type}, including the background, promotional "
    "banners, decorative elements, unrelated text, people, hands, props, "
    "furniture, other products, shadows from surrounding objects, and any "
    "unrelated objects. Do not redesign, regenerate, replace, stylize, "
    "enhance, deform, crop, or alter the {product_type}. Do not invent "
    "missing parts. Keep the original appearance, orientation, perspective, "
    "scale, and visible details unchanged. Output only the complete "
    "{product_type} with clean, precise edges and a fully transparent "
    "background."
)


def build_edit_image_prompt(product_type: str) -> str:
    """Format isolation prompt for the specified product category."""
    clean_type = (
        product_type.strip() if product_type and product_type.strip()
        else "product"
    )
    return QWEN_EDIT_IMAGE_PROMPT_TEMPLATE.format(product_type=clean_type)


def build_group_edit_prompt(
    products: list[dict[str, Any]] | list[str],
) -> str:
    """Build a composite 3D studio prompt for up to 3 products in a group."""
    if not products:
        raise ValueError("Products list must not be empty")

    clean_items: list[dict[str, str]] = []
    for item in products:
        if isinstance(item, dict):
            name = str(
                item.get("name") or item.get("category_name") or "product"
            ).strip()
            cat = str(item.get("category_name") or "").strip()
            brand = str(item.get("brand") or "").strip()
            clean_items.append({"name": name, "category": cat, "brand": brand})
        else:
            clean_items.append({
                "name": str(item).strip(), "category": "", "brand": "",
            })

    if len(clean_items) == 1:
        prod_name = clean_items[0]["name"]
        cat_name = clean_items[0]["category"]
        desc = prod_name
        if cat_name and cat_name.lower() not in prod_name.lower():
            desc = f"{prod_name} ({cat_name})"
        return (
            f"Identify and isolate the main product in the provided "
            f"Image 1: {desc}. Preserve the product exactly as it appears in "
            "the original image, including its physical shape, proportions, "
            "true colors, materials, surface details, logos, labels, "
            "screens, and all components. Remove the original background, "
            "promotional banners, hands, text, props, and unrelated objects. "
            "Present it as a photorealistic 3D studio product photograph with "
            "realistic 3D depth, perspective, natural soft studio lighting, "
            "subtle reflections, and realistic contact shadows on a clean, "
            "solid plain white background. Ensure clean, sharp, precise edges."
        )

    image_descriptions = []
    for idx, item in enumerate(clean_items, start=1):
        name = item["name"]
        cat = item["category"]
        desc = f"Image {idx} is {name}"
        if cat and cat.lower() not in name.lower():
            desc += f" ({cat})"
        image_descriptions.append(desc)

    mapping_text = ", ".join(image_descriptions)
    n = len(clean_items)
    return (
        f"Identify the main product in each of the provided {n} images: "
        f"{mapping_text}. Composite, merge, and arrange all {n} products "
        "together into a single cohesive photorealistic 3D studio product "
        "photograph. Arrange them harmoniously side-by-side with realistic "
        "3D depth, perspective, unified soft studio lighting from a "
        "consistent angle, matching reflections, and natural ground contact "
        "shadows on a clean, solid plain white background. Preserve the exact "
        "physical shape, proportions, true colors, materials, surface "
        "textures, screens, displays, logos, and branding of each original "
        "product without deformation or missing parts. Remove all original "
        "backgrounds, props, promotional banners, hands, and unrelated "
        f"objects from each input image. Ensure all {n} products are clearly "
        "visible, clean, sharp, and properly scaled relative to each other."
    )


def build_group_image_prompt(descriptions: list[str]) -> str:
    """Describe only the supplied products, without unrelated object names."""
    if not descriptions or any(not text.strip() for text in descriptions):
        raise ValueError("Product descriptions must not be empty")
    if len(descriptions) == 1:
        subject = (
            f"A single {descriptions[0]}. Only one physical product, "
            "shown once and centered."
        )
    else:
        subject = (
            "These products together: " + "; ".join(descriptions)
            + ". One unit of each described product, clearly separated "
            "in one cohesive photograph."
        )
    prompt = f"{subject} {PRODUCT_PHOTO_STYLE}"
    if len(prompt) > 4000:
        raise ValueError(
            "Product prompt exceeds the API limit of 4000 characters"
        )
    return prompt


def build_group_image_prompts(descriptions: list[str]) -> list[str]:
    """Generate each product separately; compose the complete group in code."""
    if not descriptions:
        raise ValueError("A group requires product descriptions")
    return [
        build_group_image_prompt([description]) for description in descriptions
    ]
