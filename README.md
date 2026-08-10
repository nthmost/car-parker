# Car Parker

A self-contained Home Assistant integration for San Francisco street sweeping reminders.

Tell it where you parked. It tells you when the sweeper comes — and fires an alert when it's imminent.

Data source: [DataSF street sweeping schedule](https://data.sfgov.org/City-Infrastructure/Street-Sweeping-Schedule/yhqp-riqs) and [parking regulations](https://data.sfgov.org/Transportation/Parking-Regulations/hi6h-neyh).

---

## Installation

### Via HACS (recommended)

1. In HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/nthmost/car-parker` as type **Integration**
3. Install **Car Parker** and restart HA

### Manual

Copy `custom_components/car_parker/` into your HA `config/custom_components/` directory and restart.

### Configure

Go to **Settings → Devices & Services → Add Integration → Car Parker**.

On first run, ~35 MB of SFMTA street sweeping and parking data is downloaded from DataSF and stored in `/config/car_parker/`. This happens once. Use the `car_parker.sync_data` service to refresh it when schedules change (a few times a year is typical).

---

## Dashboard

A ready-made Lovelace dashboard is in `dashboard/parking.yaml`. It requires the [custom:button-card](https://github.com/custom-cards/button-card) HACS frontend component.

**Features:**
- GPS-based parking with block + side disambiguation
- Color-coded sweep countdown (green → amber → orange → red as the deadline approaches)
- Urgent alert banner when sweeping is imminent
- Maps link (uses GPS coords if available, falls back to street-name search)
- Manual text entry as a fallback

**Setup:** Register the dashboard in `configuration.yaml`:

```yaml
lovelace:
  mode: storage
  dashboards:
    car-parker:
      mode: yaml
      title: Parking
      icon: mdi:car
      show_in_sidebar: true
      filename: dashboards/parking.yaml
```

Copy `dashboard/parking.yaml` to your HA config directory and edit the one line that references your person entity:

```yaml
entity_id: person.YOUR_NAME  # replace with your person entity
```

**Manual entry** needs two companion pieces (both in `dashboard/`):

- `car_parker.helper.yaml` — the `input_text.car_parker_manual_text` helper the field writes to. Add it under your `input_text:` config, or create the equivalent helper in Settings → Devices & Services → Helpers.
- `car_parker.automation.yaml` — an automation that parks when you type a location and press **Enter**. It triggers on the field's committed value, which is deliberate: a dashboard button that reads the field directly fires before the value round-trips through HA and silently sends an empty string on first use.

---

## How it works

When you park, you either tap **Park here** (GPS) or type your location manually. For GPS, the integration looks up the nearest block faces in the SFMTA dataset and asks you to confirm which block and which side of the street you're on — GPS alone isn't precise enough to know that reliably.

Once confirmed, it computes the next scheduled sweep for your exact block face and side, and keeps a running countdown. The `binary_sensor.move_car_now` entity flips on when urgency reaches `urgent` (< 2 hours by default) or `now`, which you can use to trigger a push notification via a standard HA automation.

---

## Urgency thresholds

The urgency levels are configurable. Go to **Settings → Devices & Services → Car Parker → Configure** to set:

| Option | Default | Meaning |
|---|---|---|
| **Urgent when within (hours)** | 2 | A sweep this many hours away or less is `urgent` and turns on `binary_sensor.move_car_now`. |
| **Soon when within (days)** | 1 | A sweep this many days away or less (but not yet urgent) is `soon`. `0` = only today counts as soon; `1` = today and tomorrow. |

Changes apply immediately (the integration reloads itself). `now` (sweep already started) and `safe` (everything beyond the `soon` window) are derived automatically.

---

## Entities

| Entity | Type | Description |
|---|---|---|
| `sensor.car_parker_status` | sensor | `empty` / `pending` / `parked` |
| `sensor.car_parker_urgency` | sensor | `safe` / `soon` / `urgent` / `now` |
| `sensor.next_street_sweep` | timestamp | Next sweep start (use for automations) |
| `sensor.next_street_sweep_label` | sensor | Human-readable label, e.g. "Tuesday, Jun 3rd 7–9am" |
| `sensor.parked_location` | sensor | Street, block, and side |
| `sensor.parking_time_limit` | sensor | Nearby time-limit restriction, if any |
| `binary_sensor.car_parked` | binary | On when status is `parked` |
| `binary_sensor.move_car_now` | binary | On when urgency is `urgent` or `now` — use this for push alerts |
| `binary_sensor.car_parker_needs_side_confirmation` | binary | On during the GPS confirmation flow |

---

## Services

| Service | Description |
|---|---|
| `car_parker.park_here` | Start GPS flow — pass `entity_id: person.x` or explicit `latitude`/`longitude` |
| `car_parker.pick_block` | Confirm which nearby block you're on (GPS flow, stage 2) |
| `car_parker.confirm_side` | Confirm which side of the street (GPS flow, stage 3) |
| `car_parker.park_manual` | Set location by free text (`"Anza between 7th and 8th, north side"`) or structured `street`/`block`/`side` |
| `car_parker.clear` | Forget the current parking spot |
| `car_parker.sync_data` | Re-download SFMTA data from DataSF |

---

## Push notification example

```yaml
automation:
  - alias: Move car alert
    trigger:
      - platform: state
        entity_id: binary_sensor.move_car_now
        to: 'on'
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: Move your car
          message: >
            Street sweeping soon —
            {{ states('sensor.next_street_sweep_label') }}
```

---

## Standalone backend (optional)

The `backend/` directory contains a standalone Flask API for the same functionality, if you'd rather run it as a separate service (e.g. without HA). See `backend/app.py` and `backend/sync.py`. It is not required for the HA integration.

---

## License

MIT
