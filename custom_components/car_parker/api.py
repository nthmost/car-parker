"""Async REST client for the car-parker API."""

from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)


class CarParkerApiError(Exception):
    """Raised when the car-parker API returns a non-2xx response."""


class CarParkerApiClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str):
        self._session = session
        self._base = base_url.rstrip("/")

    async def _request(
        self, method: str, path: str, json: Optional[dict] = None
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        async with self._session.request(method, url, json=json, timeout=10) as resp:
            body = await resp.json()
            if resp.status >= 400:
                msg = body.get("error") if isinstance(body, dict) else str(body)
                raise CarParkerApiError(f"{method} {path} → {resp.status}: {msg}")
            return body

    async def get_status(self) -> dict[str, Any]:
        return await self._request("GET", "/api/status")

    async def park_tentative(self, lat: float, lng: float) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/park/tentative", json={"lat": lat, "lng": lng}
        )

    async def park_pick_block(
        self, street: str, limits: Optional[str]
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"street": street}
        if limits is not None:
            payload["limits"] = limits
        return await self._request("POST", "/api/park/pick_block", json=payload)

    async def park_confirm(self, side: str) -> dict[str, Any]:
        return await self._request("POST", "/api/park/confirm", json={"side": side})

    async def park_text(self, text: str) -> dict[str, Any]:
        return await self._request("POST", "/api/park", json={"text": text})

    async def park_structured(
        self, street: str, block: Optional[str], side: str
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"street": street, "side": side}
        if block:
            payload["block"] = block
        return await self._request("POST", "/api/park", json=payload)

    async def clear(self) -> dict[str, Any]:
        return await self._request("POST", "/api/clear")
