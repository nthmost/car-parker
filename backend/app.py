#!/usr/bin/env python3
"""
car-parker: SF street sweeping API.

Two-phase park flow for GPS-triggered parking:
  POST /api/park/tentative  { "lat": ..., "lng": ... }
      → returns candidate block + valid sides, stashes pending state
  POST /api/park/confirm    { "side": "North" }
      → finalizes the pending state with the chosen side

One-shot flows (no disambiguation needed):
  POST /api/park            { "text": "..." } | { "street", "block", "side" }

State:
  GET  /api/status          → { "status": "empty" | "pending" | "parked", ... }
  POST /api/clear

Autocomplete (web UI):
  GET  /api/streets?q=...
  GET  /api/blocks?street=...
  GET  /api/sides?street=...&block=...
"""

import logging
from flask import Flask, jsonify, request

from parking import StreetSweepingLookup, ParkingManager
from parking_geo import TimeLimitLookup, SweepingGeoLookup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Module-level singletons, lazily initialized.
_lookup: StreetSweepingLookup = None
_manager: ParkingManager = None
_timelimit: TimeLimitLookup = None
_sweeping_geo: SweepingGeoLookup = None


def get_manager() -> ParkingManager:
    global _lookup, _manager
    if _manager is None:
        _lookup = StreetSweepingLookup()
        _manager = ParkingManager(_lookup)
    return _manager


def get_geo():
    global _timelimit, _sweeping_geo
    if _timelimit is None:
        _timelimit = TimeLimitLookup()
        _sweeping_geo = SweepingGeoLookup()
    return _timelimit, _sweeping_geo


# ── API: status / clear ────────────────────────────────────────────────────

@app.route('/api/status')
def api_status():
    try:
        return jsonify(get_manager().get_status())
    except FileNotFoundError as e:
        return jsonify({'error': str(e), 'data_missing': True}), 503


@app.route('/api/clear', methods=['POST'])
def api_clear():
    get_manager().clear()
    return jsonify(get_manager().get_status())


# ── API: two-phase GPS park ────────────────────────────────────────────────

@app.route('/api/park/tentative', methods=['POST'])
def api_park_tentative():
    """Capture GPS, return nearby candidate blocks (stage=pick_block)."""
    data = request.get_json(force=True) or {}
    if 'lat' not in data or 'lng' not in data:
        return jsonify({'error': 'lat and lng required'}), 400

    lat, lng = float(data['lat']), float(data['lng'])
    mgr = get_manager()
    tl_lookup, sw_geo = get_geo()

    tl = tl_lookup.find_nearest(lat, lng)
    time_limit = tl.to_dict() if tl else None

    nearby_blocks = sw_geo.find_nearby_blocks(lat, lng, max_blocks=5)
    mgr.save_tentative(lat, lng, nearby_blocks, time_limit)
    return jsonify(mgr.get_status())


@app.route('/api/park/pick_block', methods=['POST'])
def api_park_pick_block():
    """Transition pending pick_block → pick_side by choosing a block."""
    data = request.get_json(force=True) or {}
    street = data.get('street')
    limits = data.get('limits')
    if not street:
        return jsonify({'error': 'street required'}), 400

    mgr = get_manager()
    try:
        result = mgr.pick_block(street, limits)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    if result is None:
        return jsonify({'error': 'No pick_block stage to advance'}), 409
    return jsonify(mgr.get_status())


@app.route('/api/park/confirm', methods=['POST'])
def api_park_confirm():
    """Finalize a pending/pick_side park by locking in the chosen side."""
    data = request.get_json(force=True) or {}
    side = data.get('side')
    if not side:
        return jsonify({'error': 'side required'}), 400

    mgr = get_manager()
    try:
        result = mgr.confirm_side(side)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    if result is None:
        return jsonify({'error': 'No pick_side stage to confirm'}), 409
    return jsonify(mgr.get_status())


# ── API: one-shot manual park (text / structured) ──────────────────────────

@app.route('/api/park', methods=['POST'])
def api_park():
    """One-shot park from text or structured form data.

    For GPS, use /api/park/tentative + /api/park/confirm instead.
    """
    data = request.get_json(force=True) or {}
    mgr = get_manager()

    if 'text' in data:
        location = mgr.parser.parse(data['text'])
        if not location:
            return jsonify({
                'error': 'Could not parse location. Try: '
                         '"Anza between 7th and 8th" or use the dropdowns.'
            }), 400
        mgr.save_parking_location(location)
        return jsonify(mgr.get_status())

    if 'street' in data:
        street = data['street']
        block = data.get('block') or None
        side = data.get('side', 'Unknown')
        matched = mgr.lookup.find_street(street)
        if not matched:
            return jsonify({'error': f'Street not found: {street}'}), 400
        mgr.save_structured_location(matched, block, side)
        return jsonify(mgr.get_status())

    return jsonify({
        'error': 'Provide text or street field. '
                 'For GPS use /api/park/tentative.'
    }), 400


# ── API: autocomplete ──────────────────────────────────────────────────────

@app.route('/api/streets')
def api_streets():
    q = request.args.get('q', '').strip()
    mgr = get_manager()
    if q:
        return jsonify(mgr.lookup.find_streets_prefix(q))
    return jsonify(mgr.lookup.get_street_names())


@app.route('/api/blocks')
def api_blocks():
    street = request.args.get('street', '').strip()
    if not street:
        return jsonify([])
    return jsonify(get_manager().lookup.get_all_blocks_for_street(street))


@app.route('/api/sides')
def api_sides():
    street = request.args.get('street', '').strip()
    block = request.args.get('block', '').strip() or None
    if not street:
        return jsonify([])
    return jsonify(get_manager().lookup.get_valid_sides(street, block))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=True)
