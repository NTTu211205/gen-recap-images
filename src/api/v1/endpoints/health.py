# Report API process health without calling downstream MWG services.

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
