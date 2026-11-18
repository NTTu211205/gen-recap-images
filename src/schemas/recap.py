# Define the public recap input types and JSON error response.

from typing import Annotated, Any

from pydantic import BaseModel, StringConstraints

ProductCode = Annotated[str, StringConstraints(
    strict=True, strip_whitespace=True, min_length=1, max_length=32,
    pattern=r"^[0-9]+$",
)]


class ErrorResponse(BaseModel):
    detail: str | dict[str, Any] | list[dict[str, Any]]
