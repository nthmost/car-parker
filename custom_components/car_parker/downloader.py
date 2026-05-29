"""Download SFMTA street sweeping and parking data from DataSF."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

_DATASETS = [
    (
        "https://data.sfgov.org/resource/yhqp-riqs.json?$limit=50000",
        "street_sweeping_sf.json",
    ),
    (
        "https://data.sfgov.org/resource/hi6h-neyh.geojson?$limit=50000",
        "parking_regulations_sf.geojson",
    ),
]

_TIMEOUT = aiohttp.ClientTimeout(total=120)


async def download_all(hass: HomeAssistant, data_dir: Path) -> None:
    """Download both SFMTA datasets into data_dir."""
    data_dir.mkdir(parents=True, exist_ok=True)
    session = async_get_clientsession(hass)
    for url, filename in _DATASETS:
        dest = data_dir / filename
        _LOGGER.info("Downloading %s → %s", url, dest)
        async with session.get(url, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            content = await resp.read()
        await hass.async_add_executor_job(dest.write_bytes, content)
        _LOGGER.info("Saved %s (%d bytes)", filename, len(content))
    meta = {"downloaded_at": datetime.now(timezone.utc).isoformat()}
    meta_path = data_dir / "sync_metadata.json"
    await hass.async_add_executor_job(
        meta_path.write_text, json.dumps(meta, indent=2)
    )


def data_age_days(data_dir: Path) -> float | None:
    """Return age of downloaded data in days, or None if never downloaded."""
    meta_path = data_dir / "sync_metadata.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text())
        downloaded_at = datetime.fromisoformat(meta["downloaded_at"])
        age = datetime.now(timezone.utc) - downloaded_at
        return age.total_seconds() / 86400
    except Exception:
        return None
