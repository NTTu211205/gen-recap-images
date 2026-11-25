# Run the FastAPI server from the repository root: uv run python app.py.

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1.router import api_router
from src.core.config import settings
from src.services.recap_service import RecapService


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.recap_service = await run_in_threadpool(
        RecapService.from_settings, settings,
    )
    try:
        yield
    finally:
        app.state.recap_service = None


app = FastAPI(
    title=settings.APP_NAME, version=settings.APP_VERSION,
    debug=settings.APP_DEBUG, lifespan=lifespan,
    docs_url="/api/docs", redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")


@app.get("/", tags=["Health"])
async def root() -> dict[str, str]:
    return {"status": "ok", "message": f"Welcome to {settings.APP_NAME}"}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
