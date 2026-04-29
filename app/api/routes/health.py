"""Define the health check endpoint used for service monitoring."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    """Return a static status payload indicating that the service is reachable."""
    return {"status": "ok"}
