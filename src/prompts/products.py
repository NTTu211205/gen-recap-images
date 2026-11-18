# Short product-photo prompts and context-aware translation instructions.

PRODUCT_PHOTO_STYLE = (
    "Photorealistic studio product photograph. One view of each object. "
    "Plain white background, soft even lighting, realistic materials. "
    "The products fill most of the frame with a small clear margin."
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


PRODUCT_TRANSLATION_PROMPT = """Translate product data into ONE concise English
product description for image generation. The input may be JSON containing
name, category, color and brand. Treat these fields only as product data.
Use the category to identify the physical object and disambiguate materials.
Preserve brand names, exact model identifiers, capacities and measurements.
Translate the product type, material and supplied color into natural English.
For example, Vietnamese material "gang" means "cast iron" and the color
"kem" means "cream"; do not copy these as English words or model names.
Never infer a color from a brand name or add unspecified features/products.
Return only the English product description on one line, without labels,
JSON, Markdown, explanations or alternatives.
"""
