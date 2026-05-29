#!/usr/bin/env python3
"""
GPS-based parking lookup for SF.

Finds the nearest block face in:
  - parking_regulations_sf.geojson  → time limits, RPP info
  - street_sweeping_sf.json         → sweeping schedules

Uses point-to-line-segment distance (no dependencies beyond stdlib).
"""

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
REGULATIONS_FILE = DATA_DIR / "parking_regulations_sf.geojson"
SWEEPING_FILE = DATA_DIR / "street_sweeping_sf.json"

# SF latitude for lng→meters conversion
_SF_LAT = 37.76
_LAT_M = 111_000.0                        # meters per degree latitude
_LNG_M = 111_000.0 * math.cos(math.radians(_SF_LAT))  # meters per degree longitude


def _dist_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Fast planar approximation of distance in metres (good to ~1% within SF)."""
    dlat = (lat2 - lat1) * _LAT_M
    dlng = (lng2 - lng1) * _LNG_M
    return math.sqrt(dlat * dlat + dlng * dlng)


def _point_to_segment_dist(
    px: float, py: float,       # query point (lng, lat)
    ax: float, ay: float,       # segment start
    bx: float, by: float,       # segment end
) -> float:
    """Distance in metres from point P to line segment AB."""
    dax = (ax - px) * _LNG_M
    day = (ay - py) * _LAT_M
    dbx = (bx - ax) * _LNG_M
    dby = (by - ay) * _LAT_M
    seg_len2 = dbx * dbx + dby * dby
    if seg_len2 == 0:
        return math.sqrt(dax * dax + day * day)
    t = max(0.0, min(1.0, -(dax * dbx + day * dby) / seg_len2))
    cx = dax + t * dbx
    cy = day + t * dby
    return math.sqrt(cx * cx + cy * cy)


def _nearest_dist_to_multilinestring(
    lng: float, lat: float, coords: List[List[List[float]]]
) -> float:
    """Minimum distance from point to a MultiLineString."""
    best = float("inf")
    for ring in coords:
        for i in range(len(ring) - 1):
            d = _point_to_segment_dist(lng, lat, ring[i][0], ring[i][1], ring[i + 1][0], ring[i + 1][1])
            if d < best:
                best = d
    return best


def _nearest_dist_to_linestring(
    lng: float, lat: float, coords: List[List[float]]
) -> float:
    """Minimum distance from point to a LineString."""
    best = float("inf")
    for i in range(len(coords) - 1):
        d = _point_to_segment_dist(lng, lat, coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        if d < best:
            best = d
    return best


def _feature_midpoint(coords: List[List[List[float]]]) -> Tuple[float, float]:
    """Compute centroid of first ring of a MultiLineString (lng, lat)."""
    ring = coords[0]
    lng = sum(c[0] for c in ring) / len(ring)
    lat = sum(c[1] for c in ring) / len(ring)
    return lng, lat


# ── Time-limit regulations ──────────────────────────────────────────────────

@dataclass
class TimeLimitInfo:
    hrlimit: Optional[float]       # e.g. 2.0
    days: Optional[str]            # e.g. "M-F"
    from_time: Optional[str]       # e.g. "8am"
    to_time: Optional[str]         # e.g. "6pm"
    rpp_exempt: bool               # RPP holders exempt?
    rpp_areas: List[str]           # e.g. ["L"]
    regulation: str                # raw regulation type
    distance_m: float

    def to_dict(self) -> dict:
        return {
            "hrlimit": self.hrlimit,
            "days": self.days,
            "from_time": self.from_time,
            "to_time": self.to_time,
            "rpp_exempt": self.rpp_exempt,
            "rpp_areas": self.rpp_areas,
            "regulation": self.regulation,
            "distance_m": round(self.distance_m),
        }

    def human_readable(self) -> str:
        if self.hrlimit and self.hrlimit > 0:
            h = int(self.hrlimit) if self.hrlimit == int(self.hrlimit) else self.hrlimit
            s = f"{h}-hour parking"
            if self.from_time and self.to_time:
                s += f" {self.from_time}–{self.to_time}"
            if self.days:
                s += f" ({self.days})"
            if self.rpp_exempt and self.rpp_areas:
                areas = ", ".join(a for a in self.rpp_areas if a)
                s += f" — RPP area {areas} exempt"
            return s
        return self.regulation or "Parking restriction"


class TimeLimitLookup:
    """Looks up time-limit parking rules nearest to a GPS point."""

    # Tight threshold: a regulation on the curb you're at should be within
    # ~10m (GPS noise) + a couple meters slop. 80m+ leaks across streets.
    MAX_DISTANCE_M = 25

    def __init__(self, geojson_file: Optional[Path] = None):
        self.geojson_file = geojson_file or REGULATIONS_FILE
        self._features: List[Dict[str, Any]] = []   # list of {midpoint, coords, props}
        self._load()

    def _load(self):
        if not self.geojson_file.exists():
            raise FileNotFoundError(f"Parking regulations not found: {self.geojson_file}")
        with open(self.geojson_file) as f:
            data = json.load(f)
        count = 0
        for feature in data["features"]:
            geom = feature.get("geometry")
            if not geom or geom["type"] != "MultiLineString":
                continue
            coords = geom["coordinates"]
            if not coords or not coords[0]:
                continue
            mid = _feature_midpoint(coords)
            self._features.append({
                "midpoint": mid,
                "coords": coords,
                "props": feature["properties"],
            })
            count += 1
        logger.info(f"Loaded {count} parking regulation features")

    def find_nearest(self, lat: float, lng: float) -> Optional[TimeLimitInfo]:
        """Return the nearest time-limit regulation within MAX_DISTANCE_M."""
        best_dist = float("inf")
        best_props = None

        for feat in self._features:
            # Fast coarse filter using midpoint
            mlng, mlat = feat["midpoint"]
            coarse = _dist_m(lat, lng, mlat, mlng)
            if coarse > self.MAX_DISTANCE_M * 3:
                continue
            # Exact segment distance
            d = _nearest_dist_to_multilinestring(lng, lat, feat["coords"])
            if d < best_dist:
                best_dist = d
                best_props = feat["props"]

        if best_props is None or best_dist > self.MAX_DISTANCE_M:
            return None

        p = best_props
        hrlimit = None
        try:
            v = p.get("hrlimit")
            if v is not None:
                hrlimit = float(v)
        except (TypeError, ValueError):
            pass

        rpp_areas = [p.get(k) for k in ("rpparea1", "rpparea2", "rpparea3") if p.get(k)]
        exceptions = (p.get("exceptions") or "").lower()
        rpp_exempt = "rpp" in exceptions or "exempt" in exceptions

        return TimeLimitInfo(
            hrlimit=hrlimit,
            days=p.get("days"),
            from_time=p.get("from_time"),
            to_time=p.get("to_time"),
            rpp_exempt=rpp_exempt,
            rpp_areas=rpp_areas,
            regulation=p.get("regulation", ""),
            distance_m=best_dist,
        )


# ── Sweeping lookup by GPS ──────────────────────────────────────────────────

class SweepingGeoLookup:
    """GPS-based sweeping lookup using the line geometry in the sweeping dataset."""

    MAX_DISTANCE_M = 80

    def __init__(self, sweeping_file: Optional[Path] = None):
        self.sweeping_file = sweeping_file or SWEEPING_FILE
        self._features: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if not self.sweeping_file.exists():
            raise FileNotFoundError(f"Sweeping data not found: {self.sweeping_file}")
        with open(self.sweeping_file) as f:
            records = json.load(f)
        for r in records:
            line = r.get("line")
            if not line or line.get("type") != "LineString":
                continue
            coords = line["coordinates"]
            if len(coords) < 2:
                continue
            # midpoint
            mlng = sum(c[0] for c in coords) / len(coords)
            mlat = sum(c[1] for c in coords) / len(coords)
            self._features.append({
                "midpoint": (mlng, mlat),
                "coords": coords,
                "record": r,
            })
        logger.info(f"Loaded {len(self._features)} sweeping geo features")

    def find_nearest_records(self, lat: float, lng: float) -> List[Dict]:
        """Return all sweeping records on the nearest block (within threshold)."""
        candidates = []
        for feat in self._features:
            mlng, mlat = feat["midpoint"]
            coarse = _dist_m(lat, lng, mlat, mlng)
            if coarse > self.MAX_DISTANCE_M * 3:
                continue
            d = _nearest_dist_to_linestring(lng, lat, feat["coords"])
            if d <= self.MAX_DISTANCE_M:
                candidates.append((d, feat["record"]))

        if not candidates:
            return []

        # Group by CNN to get the nearest block, then return all records for that block
        candidates.sort(key=lambda x: x[0])
        nearest_cnn = candidates[0][1].get("cnn")
        return [r for d, r in candidates if r.get("cnn") == nearest_cnn]

    def find_nearby_blocks(
        self, lat: float, lng: float, max_blocks: int = 5
    ) -> List[Dict]:
        """Return up to max_blocks nearest blocks (street+limits), each with
        an aggregated list of sides found in the sweeping data.

        Each block dict:
          {
            "street": "08th Ave",
            "limits": "Geary Blvd  -  Anza St",
            "sides": ["East", "West"],
            "distance_m": 12,
          }
        Sorted by ascending distance.
        """
        scored: List[Tuple[float, Dict]] = []
        for feat in self._features:
            mlng, mlat = feat["midpoint"]
            coarse = _dist_m(lat, lng, mlat, mlng)
            if coarse > self.MAX_DISTANCE_M * 3:
                continue
            d = _nearest_dist_to_linestring(lng, lat, feat["coords"])
            if d <= self.MAX_DISTANCE_M:
                scored.append((d, feat["record"]))

        if not scored:
            return []

        scored.sort(key=lambda x: x[0])

        # Aggregate by (street, limits). First-seen distance wins (smallest).
        by_block: Dict[Tuple, Dict[str, Any]] = {}
        for dist, rec in scored:
            key = (rec.get("corridor"), rec.get("limits"))
            entry = by_block.get(key)
            side = (rec.get("blockside") or "").strip()
            if entry is None:
                by_block[key] = {
                    "street": rec.get("corridor"),
                    "limits": rec.get("limits"),
                    "sides": {side} if side else set(),
                    "distance_m": round(dist),
                }
            elif side:
                entry["sides"].add(side)

        result = sorted(by_block.values(), key=lambda b: b["distance_m"])[:max_blocks]
        for b in result:
            b["sides"] = sorted(b["sides"])
        return result
