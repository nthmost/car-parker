"""Constants for the Car Parker integration."""

DOMAIN = "car_parker"

DEFAULT_POLL_INTERVAL = 60  # seconds

# Service names
SERVICE_PARK_HERE = "park_here"
SERVICE_PARK_AT_CAR = "park_at_car"
SERVICE_PICK_BLOCK = "pick_block"
SERVICE_CONFIRM_SIDE = "confirm_side"
SERVICE_PARK_MANUAL = "park_manual"
SERVICE_CLEAR = "clear"
SERVICE_SYNC_DATA = "sync_data"

# Service param keys
ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_ENTITY_ID = "entity_id"
ATTR_SIDE = "side"
ATTR_TEXT = "text"
ATTR_STREET = "street"
ATTR_BLOCK = "block"
ATTR_LIMITS = "limits"

# Pending sub-stages
STAGE_PICK_BLOCK = "pick_block"
STAGE_PICK_SIDE = "pick_side"

# Status values from the API
STATUS_EMPTY = "empty"
STATUS_PENDING = "pending"
STATUS_PARKED = "parked"

# Options (editable in the HA UI via the Configure button)
CONF_URGENT_HOURS = "urgent_hours"
CONF_SOON_DAYS = "soon_days"
CONF_CAR_TRACKER = "car_tracker"

DEFAULT_URGENT_HOURS = 2  # < this many hours until the sweep → "urgent"
DEFAULT_SOON_DAYS = 1  # sweep within this many days (but not urgent) → "soon"

# Urgency values
URGENCY_SAFE = "safe"
URGENCY_SOON = "soon"
URGENCY_URGENT = "urgent"
URGENCY_NOW = "now"
URGENCY_AWAITING_SIDE = "awaiting_side"
