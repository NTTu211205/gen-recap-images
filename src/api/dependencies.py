# Provide application-owned services to HTTP endpoints.

from fastapi import Request

from src.services.recap_service import RecapService


async def get_recap_service(request: Request) -> RecapService:
    return request.app.state.recap_service
