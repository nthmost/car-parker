#!/usr/bin/env python3
"""
Download/cache SF parking datasets from DataSF.

Two datasets are synced:
  - Street sweeping schedule    (yhqp-riqs)  → street_sweeping_sf.json
  - Parking regulations         (hi6h-neyh)  → parking_regulations_sf.geojson

Both use Socrata's rowsUpdatedAt for cheap version checks.

Run periodically (e.g. weekly via cron/systemd timer) to refresh.
"""

import json
import logging
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

DATASETS = {
    'street_sweeping': {
        'view_id': 'yhqp-riqs',
        'output': 'street_sweeping_sf.json',
        'format': 'json',
        'approx_size': '25MB',
    },
    'parking_regulations': {
        'view_id': 'hi6h-neyh',
        'output': 'parking_regulations_sf.geojson',
        'format': 'geojson',
        'approx_size': '10MB',
    },
}


def _metadata_url(view_id: str) -> str:
    return f"https://data.sfgov.org/api/views/{view_id}.json"


def _data_url(view_id: str, fmt: str) -> str:
    return f"https://data.sfgov.org/resource/{view_id}.{fmt}?$limit=50000"


def _load_local_metadata(metadata_file: Path) -> Optional[Dict]:
    if not metadata_file.exists():
        return None
    with open(metadata_file) as f:
        return json.load(f)


def _save_local_metadata(metadata_file: Path, all_meta: Dict):
    with open(metadata_file, 'w') as f:
        json.dump(all_meta, f, indent=2)


def _sync_dataset(name: str, config: Dict, all_meta: Dict, force: bool) -> Dict:
    """Sync a single dataset. Returns dict with {updated, record_count}."""
    view_id = config['view_id']
    output_file = DATA_DIR / config['output']
    local = all_meta.get(name)

    logger.info(f"[{name}] Checking remote metadata...")
    with urllib.request.urlopen(_metadata_url(view_id), timeout=10) as resp:
        remote = json.loads(resp.read())
    remote_updated = remote['rowsUpdatedAt']
    remote_count = remote.get('rowCount', 0)

    needs_update = (
        force
        or local is None
        or not output_file.exists()
        or remote_updated > local.get('rows_updated_at', 0)
    )

    if not needs_update:
        logger.info(f"[{name}] Up to date ({local.get('record_count', '?')} records)")
        return {'updated': False, 'record_count': local.get('record_count', 0)}

    logger.info(f"[{name}] Downloading (~{config['approx_size']})...")
    with urllib.request.urlopen(_data_url(view_id, config['format']), timeout=120) as resp:
        raw = resp.read()

    with open(output_file, 'wb') as f:
        f.write(raw)

    if config['format'] == 'geojson':
        record_count = len(json.loads(raw).get('features', []))
    else:
        record_count = len(json.loads(raw))

    all_meta[name] = {
        'last_sync': datetime.now(timezone.utc).isoformat(),
        'rows_updated_at': remote_updated,
        'remote_row_count': remote_count,
        'record_count': record_count,
    }

    logger.info(f"[{name}] Downloaded {record_count} records")
    return {'updated': True, 'record_count': record_count}


def sync(force: bool = False) -> Dict[str, Dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    metadata_file = DATA_DIR / "sync_metadata.json"
    all_meta = _load_local_metadata(metadata_file) or {}

    # Migration: old single-dataset metadata format was flat (no per-dataset key).
    if 'rows_updated_at' in all_meta and 'street_sweeping' not in all_meta:
        all_meta = {'street_sweeping': all_meta}

    results = {}
    for name, config in DATASETS.items():
        results[name] = _sync_dataset(name, config, all_meta, force)

    _save_local_metadata(metadata_file, all_meta)
    return results


if __name__ == '__main__':
    force = '--force' in sys.argv
    results = sync(force=force)
    for name, result in results.items():
        marker = '↻' if result['updated'] else '✓'
        print(f"  {marker} {name}: {result['record_count']} records")
