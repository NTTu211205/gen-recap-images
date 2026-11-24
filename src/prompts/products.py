# Short product-photo prompts for image editing and generation.

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
