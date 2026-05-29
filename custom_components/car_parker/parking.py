#!/usr/bin/env python3
"""
SF Parking and Street Sweeping lookup.

State model (parking_state.json):
  absent file                            — empty (not parked)
  {"status": "pending", ...}             — GPS captured, awaiting side confirmation
  {"status": "parked", ...}              — fully confirmed
"""

import json
import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from difflib import get_close_matches
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
SWEEPING_DATA_FILE = DATA_DIR / "street_sweeping_sf.json"
PARKING_STATE_FILE = DATA_DIR / "parking_state.json"

# All SFMTA times are local clock time; we anchor here so DST is correct.
LOCAL_TZ = ZoneInfo("America/Los_Angeles")

WEEK_FIELDS = ['week1', 'week2', 'week3', 'week4', 'week5']


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def now_local_iso() -> str:
    return now_local().isoformat()


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"


def _normalize_side(side: Optional[str]) -> str:
    if not side:
        return "Unknown"
    s = side.strip().title()
    return s or "Unknown"


# ── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class ParkingLocation:
    street: str
    cross_street_1: Optional[str]
    cross_street_2: Optional[str]
    side: str  # North, South, East, West, Unknown
    block_limits: Optional[str]  # e.g., "07th Ave  -  08th Ave"
    timestamp: str
    raw_input: str


@dataclass
class SweepingSchedule:
    corridor: str
    limits: str
    blockside: str
    weekday: str
    fullname: str
    fromhour: int
    tohour: int
    week1: bool
    week2: bool
    week3: bool
    week4: bool
    week5: bool
    holidays: bool

    _WEEKDAY_NORM = {'Tues': 'Tue', 'Thurs': 'Thu'}

    def applies_to_date(self, date: datetime) -> bool:
        weekday = self._WEEKDAY_NORM.get(self.weekday, self.weekday)
        if date.strftime('%a') != weekday:
            return False
        week_of_month = min(5, (date.day - 1) // 7 + 1)
        weeks = [self.week1, self.week2, self.week3, self.week4, self.week5]
        return weeks[week_of_month - 1]

    def get_datetime_range(self, date: datetime) -> Tuple[datetime, datetime]:
        # Preserve tz from `date`; SFMTA hours are local clock time.
        start = date.replace(hour=self.fromhour, minute=0, second=0, microsecond=0)
        end = date.replace(hour=self.tohour, minute=0, second=0, microsecond=0)
        return start, end

    def weeks_description(self) -> str:
        weeks = []
        for i, applies in enumerate(
            [self.week1, self.week2, self.week3, self.week4, self.week5], 1
        ):
            if applies:
                weeks.append(ordinal(i))
        return ', '.join(weeks)

    def to_dict(self) -> dict:
        return {
            'corridor': self.corridor,
            'limits': self.limits,
            'blockside': self.blockside,
            'weekday': self.weekday,
            'fullname': self.fullname,
            'fromhour': self.fromhour,
            'tohour': self.tohour,
            'weeks': self.weeks_description(),
            'holidays': self.holidays,
        }


# ── Sweeping data lookup ────────────────────────────────────────────────────

class StreetSweepingLookup:
    def __init__(self, data_file: Optional[Path] = None):
        self.data_file = data_file or SWEEPING_DATA_FILE
        self.data: List[Dict] = []
        self.street_index: Dict[str, List[Dict]] = {}
        self._load_data()

    def _load_data(self):
        if not self.data_file.exists():
            raise FileNotFoundError(
                f"Street sweeping data not found at {self.data_file}. "
                f"Run: python sync.py"
            )
        with open(self.data_file, 'r') as f:
            self.data = json.load(f)
        for record in self.data:
            street = record['corridor']
            self.street_index.setdefault(street, []).append(record)
        logger.info(
            f"Loaded {len(self.data)} records covering {len(self.street_index)} streets"
        )

    def get_street_names(self) -> List[str]:
        return sorted(self.street_index.keys())

    def find_street(self, street_query: str) -> Optional[str]:
        street_query = street_query.strip().title()
        if street_query in self.street_index:
            return street_query
        for suffix in [' St', ' Ave', ' Blvd', ' Dr', ' Way', ' Ln']:
            candidate = street_query + suffix
            if candidate in self.street_index:
                return candidate
        matches = get_close_matches(
            street_query, self.street_index.keys(), n=3, cutoff=0.6
        )
        return matches[0] if matches else None

    def find_streets_prefix(self, prefix: str, limit: int = 20) -> List[str]:
        prefix = prefix.strip().lower()
        # Also try zero-padded form: "9th" -> "09th"
        padded = re.sub(
            r'^(\d)(st|nd|rd|th)', lambda m: f'0{m.group(1)}{m.group(2)}', prefix
        )
        results = [
            s for s in self.get_street_names()
            if s.lower().startswith(prefix)
            or (padded != prefix and s.lower().startswith(padded))
        ]
        return results[:limit]

    def get_valid_sides(
        self, street: str, block_limits: Optional[str] = None
    ) -> List[str]:
        street_name = self.find_street(street)
        if not street_name:
            return []
        records = self.street_index.get(street_name, [])
        if block_limits:
            records = [r for r in records if r['limits'] == block_limits]
        sides = {r.get('blockside', '').strip() for r in records if r.get('blockside')}
        return sorted(sides)

    def lookup_schedule(
        self,
        street: str,
        block_limits: Optional[str] = None,
        side: Optional[str] = None,
    ) -> List[SweepingSchedule]:
        street_name = self.find_street(street)
        if not street_name:
            return []
        records = self.street_index.get(street_name, [])
        if block_limits:
            records = [r for r in records if r['limits'] == block_limits]
        if side and side.lower() != 'unknown':
            records = [
                r for r in records
                if r.get('blockside', '').lower() == side.lower()
            ]
        return [self._record_to_schedule(r) for r in records]

    @staticmethod
    def _record_to_schedule(r: Dict) -> SweepingSchedule:
        return SweepingSchedule(
            corridor=r['corridor'],
            limits=r['limits'],
            blockside=r['blockside'],
            weekday=r['weekday'],
            fullname=r['fullname'],
            fromhour=int(r['fromhour']),
            tohour=int(r['tohour']),
            week1=bool(int(r['week1'])),
            week2=bool(int(r['week2'])),
            week3=bool(int(r['week3'])),
            week4=bool(int(r['week4'])),
            week5=bool(int(r['week5'])),
            holidays=bool(int(r['holidays'])),
        )

    def get_all_blocks_for_street(self, street: str) -> List[str]:
        street_name = self.find_street(street)
        if not street_name:
            return []
        return sorted({r['limits'] for r in self.street_index.get(street_name, [])})


# ── Text parsing ────────────────────────────────────────────────────────────

class LocationParser:
    # Matched after side has been extracted and stripped from the input.
    # All patterns may emit `street`, `cross1`, `cross2`.
    PATTERNS = [
        # "X between Y and Z"
        r'(?P<street>[\w\s]+?)\s+between\s+(?P<cross1>[\w\s]+?)\s+and\s+(?P<cross2>[\w\s]+?)\s*$',
        # "on X near Y"
        r'on\s+(?P<street>[\w\s]+)\s+near\s+(?P<cross1>[\w\s]+)',
        # "1234 X St"
        r'(?P<address>\d+)\s+(?P<street>[\w\s]+)',
        # bare "X St" / "X Ave"
        r'(?:on\s+)?(?P<street>[\w\s]+?)\s+(?:street|st|avenue|ave|blvd|boulevard|drive|dr|road|rd)\b',
    ]

    # Side appears as either:
    #   "north side of ..."   (prefix form)
    #   "..., north side"     (trailing, with or without "side", and with or
    #                          without the comma)
    SIDE_PREFIX_RE = re.compile(
        r'\b(?P<side>north|south|east|west)\s+side\s+of\s+', re.IGNORECASE
    )
    SIDE_TRAILING_RE = re.compile(
        r'[\s,]+(?:on\s+the\s+)?(?P<side>north|south|east|west)(?:\s+side)?\s*$',
        re.IGNORECASE,
    )

    def __init__(self, lookup: StreetSweepingLookup):
        self.lookup = lookup

    def normalize_avenue_number(self, text: str) -> str:
        def pad_number(match):
            num = match.group(1)
            suffix = match.group(2)
            return f"{int(num):02d}{suffix}"

        text = re.sub(r'\b(\d{1,2})(st|nd|rd|th)\b', pad_number, text, flags=re.IGNORECASE)
        text = re.sub(r'\b(ave|avenue)\b', 'Ave', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(st|street)\b', 'St', text, flags=re.IGNORECASE)
        return text

    def _extract_side(self, text: str) -> tuple[str, Optional[str]]:
        """Pull the side phrase out of `text`. Returns (text_without_side, side_or_None)."""
        m = self.SIDE_PREFIX_RE.search(text)
        if m:
            side = m.group('side').title()
            text = text[:m.start()] + text[m.end():]
            return text.strip(' ,'), side

        m = self.SIDE_TRAILING_RE.search(text)
        if m:
            side = m.group('side').title()
            text = text[:m.start()]
            return text.strip(' ,'), side

        return text, None

    def parse(self, location_text: str) -> Optional[ParkingLocation]:
        raw = location_text
        text = location_text.lower().strip()
        text = self.normalize_avenue_number(text)
        text, side = self._extract_side(text)

        for pattern in self.PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return self._process_match(match, raw, side_override=side)
        return None

    def _process_match(
        self, match, raw_input: str, side_override: Optional[str] = None
    ) -> Optional[ParkingLocation]:
        data = match.groupdict()
        street = (data.get('street') or '').strip()
        cross1 = (data.get('cross1') or '').strip() or None
        cross2 = (data.get('cross2') or '').strip() or None
        side = _normalize_side(side_override)

        street_name = self.lookup.find_street(street)
        if not street_name:
            return None

        block_limits = None
        if cross1 and cross2:
            cross1_norm = self.normalize_avenue_number(cross1).lower()
            cross2_norm = self.normalize_avenue_number(cross2).lower()
            for block in self.lookup.get_all_blocks_for_street(street_name):
                block_lc = block.lower()
                if cross1_norm in block_lc and cross2_norm in block_lc:
                    block_limits = block
                    break

        return ParkingLocation(
            street=street_name,
            cross_street_1=cross1,
            cross_street_2=cross2,
            side=side,
            block_limits=block_limits,
            timestamp=now_local_iso(),
            raw_input=raw_input,
        )


# ── Parking manager ─────────────────────────────────────────────────────────

class ParkingManager:
    """Owns the parking_state.json file and computes status."""

    def __init__(
        self,
        lookup: StreetSweepingLookup,
        state_file: Optional[Path] = None,
    ):
        self.lookup = lookup
        self.state_file = state_file or PARKING_STATE_FILE
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.parser = LocationParser(lookup)

    # ── State I/O ──

    def _write_state(self, state: Dict):
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def load_state(self) -> Optional[Dict]:
        if not self.state_file.exists():
            return None
        with open(self.state_file, 'r') as f:
            return json.load(f)

    def clear(self):
        if self.state_file.exists():
            self.state_file.unlink()

    # ── Save: tentative (GPS) — two-stage flow ──
    #
    # Stage 1 (save_tentative): GPS captured → stage='pick_block' with a list
    #   of nearby block candidates.
    # Stage 2 (pick_block): user picks a block → stage='pick_side' with that
    #   block's valid sides.
    # Stage 3 (confirm_side): user picks a side → status='parked'.

    def save_tentative(
        self,
        lat: float,
        lng: float,
        nearby_blocks: List[Dict],
        time_limit: Optional[Dict],
    ) -> Dict:
        """Stash a pending state from a GPS fix.

        `nearby_blocks` is a list of dicts shaped like
        `{street, limits, sides, distance_m}` — usually from
        SweepingGeoLookup.find_nearby_blocks().
        """
        state = {
            'status': 'pending',
            'stage': 'pick_block',
            'lat': lat,
            'lng': lng,
            'saved_at': now_local_iso(),
            'candidates': nearby_blocks,
            'time_limit': time_limit,
        }
        self._write_state(state)
        return state

    def pick_block(self, street: str, limits: Optional[str]) -> Optional[Dict]:
        """Transition pending state from pick_block → pick_side.

        Returns the new state, or None if not in pending/pick_block.
        Raises ValueError if (street, limits) isn't among the candidates.
        """
        state = self.load_state()
        if (
            not state
            or state.get('status') != 'pending'
            or state.get('stage') != 'pick_block'
        ):
            return None

        candidates = state.get('candidates') or []
        match = next(
            (
                c for c in candidates
                if c.get('street') == street and c.get('limits') == limits
            ),
            None,
        )
        if match is None:
            choices = [f"{c.get('street')} / {c.get('limits')}" for c in candidates]
            raise ValueError(
                f"Block {street!r} / {limits!r} is not among the nearby "
                f"candidates. Valid choices: {choices}"
            )

        state['stage'] = 'pick_side'
        state['chosen_block'] = {
            'street': match['street'],
            'limits': match['limits'],
        }
        state['candidate_sides'] = list(match.get('sides') or [])
        # Keep `candidates` around for back-out, but it's no longer the focus.
        self._write_state(state)
        return state

    def confirm_side(self, side: str) -> Optional[Dict]:
        """Promote a pending/pick_side state to parked.

        Returns the new state (status='parked'), or None if not in
        pending/pick_side. Raises ValueError if `side` is not valid for the
        chosen block.
        """
        state = self.load_state()
        if (
            not state
            or state.get('status') != 'pending'
            or state.get('stage') != 'pick_side'
        ):
            return None

        side_norm = _normalize_side(side)
        valid = state.get('candidate_sides') or []
        if valid and side_norm not in valid:
            raise ValueError(
                f"Side {side_norm!r} is not valid for this block. "
                f"Valid sides: {', '.join(valid) or '(none)'}"
            )

        block = state.get('chosen_block') or {}
        street = block.get('street') or 'Unknown'
        limits = block.get('limits')

        location = ParkingLocation(
            street=street,
            cross_street_1=None,
            cross_street_2=None,
            side=side_norm,
            block_limits=limits,
            timestamp=now_local_iso(),
            raw_input=f"GPS confirmed {side_norm} side",
        )
        self._save_parked(
            location,
            extra={
                'time_limit': state.get('time_limit'),
                'lat': state.get('lat'),
                'lng': state.get('lng'),
            },
        )
        return self.load_state()

    # ── Save: direct paths (text, structured) ──

    def save_parking_location(
        self, location: ParkingLocation, extra: Optional[Dict] = None
    ):
        self._save_parked(location, extra)

    def save_structured_location(
        self, street: str, block_limits: Optional[str], side: str
    ):
        side_norm = _normalize_side(side)
        location = ParkingLocation(
            street=street,
            cross_street_1=None,
            cross_street_2=None,
            side=side_norm,
            block_limits=block_limits,
            timestamp=now_local_iso(),
            raw_input=f"{street} {block_limits or ''} {side_norm} side",
        )
        self._save_parked(location)

    def _save_parked(
        self, location: ParkingLocation, extra: Optional[Dict] = None
    ):
        extra = extra or {}
        schedules = self.lookup.lookup_schedule(
            location.street, location.block_limits, location.side
        )
        state = {
            'status': 'parked',
            'location': asdict(location),
            'schedules': [asdict(s) for s in schedules],
            'saved_at': now_local_iso(),
            'time_limit': extra.get('time_limit'),
            'lat': extra.get('lat'),
            'lng': extra.get('lng'),
        }
        self._write_state(state)

    # ── Read: next sweeping event ──

    def get_next_sweeping(
        self, state: Optional[Dict] = None, days_ahead: int = 14
    ) -> Optional[Dict]:
        state = state or self.load_state()
        if not state or state.get('status') != 'parked':
            return None

        schedules = [SweepingSchedule(**s) for s in state.get('schedules', [])]
        if not schedules:
            return None

        now = now_local()
        next_event = None

        for day_offset in range(days_ahead):
            check_date = now + timedelta(days=day_offset)
            for schedule in schedules:
                if not schedule.applies_to_date(check_date):
                    continue
                start_time, end_time = schedule.get_datetime_range(check_date)
                if end_time < now:
                    continue
                if next_event is None or start_time < next_event['start_time']:
                    next_event = {
                        'schedule': schedule,
                        'date': check_date,
                        'start_time': start_time,
                        'end_time': end_time,
                    }
            if next_event:
                break  # stop at first day that has an event

        return next_event

    # ── Status (the main API consumer) ──

    def get_status(self) -> Dict:
        state = self.load_state()
        if not state:
            return self._status_empty()

        status_kind = state.get('status')
        if status_kind == 'pending':
            return self._status_pending(state)
        if status_kind == 'parked':
            return self._status_parked(state)

        logger.warning(f"Unknown state.status={status_kind!r}; reporting empty")
        return self._status_empty()

    @staticmethod
    def _status_empty() -> Dict:
        return {
            'status': 'empty',
            'parked': False,
            'urgency': 'safe',
        }

    @staticmethod
    def _status_pending(state: Dict) -> Dict:
        return {
            'status': 'pending',
            'parked': False,
            'urgency': 'awaiting_side',
            'stage': state.get('stage'),
            'lat': state.get('lat'),
            'lng': state.get('lng'),
            'saved_at': state.get('saved_at'),
            'candidates': state.get('candidates', []),
            'chosen_block': state.get('chosen_block'),
            'candidate_sides': state.get('candidate_sides', []),
            'time_limit': state.get('time_limit'),
        }

    def _status_parked(self, state: Dict) -> Dict:
        result = {
            'status': 'parked',
            'parked': True,
            'location': state['location'],
            'saved_at': state.get('saved_at'),
            'schedules': state.get('schedules', []),
            'next_sweeping': None,
            'time_limit': state.get('time_limit'),
            'lat': state.get('lat'),
            'lng': state.get('lng'),
            'urgency': 'safe',
        }

        next_sweep = self.get_next_sweeping(state)
        if next_sweep:
            result['next_sweeping'], result['urgency'] = self._format_next_sweep(
                next_sweep
            )
        return result

    @staticmethod
    def _format_next_sweep(next_sweep: Dict) -> Tuple[Dict, str]:
        now = now_local()
        start = next_sweep['start_time']
        end = next_sweep['end_time']
        delta = start - now

        sched = next_sweep['schedule']
        from_str = f"{sched.fromhour % 12 or 12}{'am' if sched.fromhour < 12 else 'pm'}"
        to_str = f"{sched.tohour % 12 or 12}{'am' if sched.tohour < 12 else 'pm'}"

        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            when_label, urgency = "NOW", 'now'
        elif delta.days == 0 and total_seconds < 7200:  # < 2h
            hours = total_seconds // 3600
            mins = (total_seconds % 3600) // 60
            when_label = f"in {hours}h {mins}m" if hours else f"in {mins} min"
            urgency = 'urgent'
        elif delta.days == 0:
            when_label = f"today {from_str}–{to_str}"
            urgency = 'soon'
        elif delta.days == 1:
            when_label = f"tomorrow {from_str}–{to_str}"
            urgency = 'soon'
        else:
            day_str = start.strftime('%A, %b ') + ordinal(start.day)
            when_label = f"{day_str} {from_str}–{to_str}"
            urgency = 'safe'

        return (
            {
                'when_label': when_label,
                'start_iso': start.isoformat(),
                'end_iso': end.isoformat(),
                'weekday': sched.weekday,
                'side': sched.blockside,
            },
            urgency,
        )
