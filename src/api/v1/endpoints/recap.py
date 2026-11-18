# Accept product codes and return the completed recap as a PNG file.

import logging
from typing import Annotated

import requests
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse

from src.api.dependencies import get_recap_service
from src.schemas.recap import ErrorResponse, ProductCode
from src.services.recap_service import (
    ProductSelectionError, RecapBusyError, RecapService,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Recap"])


@router.post(
    "/recap", response_class=FileResponse,
    summary="Generate a final shopping recap image",
    description=(
        "Accept 1-50 product codes as strings. Wait for generation and return "
        "an inline PNG image. If the recap has multiple pages, stack them "
        "vertically into one image. No automatic upstream retries."
    ),
    responses={
        200: {
            "description": "Final recap PNG",
            "content": {"image/png": {
                "schema": {"type": "string", "format": "binary"},
            }},
        },
        422: {"model": ErrorResponse, "description": "Invalid product codes"},
        500: {"model": ErrorResponse, "description": "Local generation error"},
        502: {"model": ErrorResponse, "description": "MWG generation failed"},
        503: {"model": ErrorResponse, "description": "Generation is busy"},
        504: {"model": ErrorResponse, "description": "MWG request timed out"},
    },
)
def generate_image(
    productcodes: Annotated[list[ProductCode], Body(
        min_length=1, max_length=50,
        examples=[["0164779000163", "0164779000164"]],
        description="Use strings to preserve leading zeroes in product codes.",
    )],
    service: Annotated[RecapService, Depends(get_recap_service)],
) -> FileResponse:
    """Run blocking network and inference work in FastAPI's thread pool."""
    try:
        path = service.generate(productcodes)
    except ProductSelectionError as error:
        raise HTTPException(422, detail={
            "message": "Some codes are missing or unsupported",
            "products": error.excluded,
        }) from None
    except RecapBusyError:
        raise HTTPException(
            503, "A recap is already being generated; try again later",
            headers={"Retry-After": "5"},
        ) from None
    except requests.Timeout:
        raise HTTPException(504, "MWG generation timed out") from None
    except (requests.RequestException, ValueError) as error:
        logger.warning("MWG generation failed (%s)", type(error).__name__)
        raise HTTPException(502, "MWG generation failed") from None
    except Exception as error:
        logger.error("Recap generation failed (%s)", type(error).__name__)
        raise HTTPException(500, "Recap generation failed") from None
    return FileResponse(
        path, media_type="image/png", filename="recap_final.png",
        content_disposition_type="inline",
        headers={"Cache-Control": "no-store"},
    )
