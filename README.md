# Car Parker

A Home Assistant integration + backend API for San Francisco street sweeping reminders.

Tell it where you parked. It tells you when the sweeper comes — and fires a `move_car_now` alert when it's imminent.

Data source: [DataSF street sweeping schedule](https://data.sfgov.org/City-Infrastructure/Street-Sweeping-Schedule/yhqp-riqs) and [parking regulations](https://data.sfgov.org/Transportation/Parking-Regulations/hi6h-neyh).

---

## Architecture

```
┌─────────────────────────┐        HTTP        ┌──────────────────────┐
│  Home Assistant         │ ──────────────────▶ │  car-parker backend  │
│  custom_components/     │        poll         │  Flask API (port 5050│
│  car_parker/            │                     │  + SFMTA data files) │
└─────────────────────────┘                     └──────────────────────┘
```

The backend runs on any machine on your LAN (a Pi, NAS, or spare laptop works fine). HA polls it every 60 seconds.

---

## Backend setup

### 1. Download SFMTA data

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 sync.py        # downloads ~35 MB of public SFMTA data into data/
```

Re-run `sync.py` periodically (monthly is plenty) to stay current with schedule changes.

### 2. Run the API

```bash
gunicorn -w 2 -b 0.0.0.0:5050 app:app
```

Or with plain Flask for testing:

```bash
python3 app.py
```

To run as a systemd service, create `/etc/systemd/system/car-parker.service`:

```ini
[Unit]
Description=Car Parker API
After=network.target

[Service]
User=your-user
WorkingDirectory=/path/to/car-parker/backend
ExecStart=/path/to/car-parker/backend/venv/bin/gunicorn -w 2 -b 0.0.0.0:5050 app:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now car-parker
```

---

## Home Assistant setup

### Via HACS (recommended)

1. In HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/nthmost/car-parker` as type **Integration**
3. Install **Car Parker**, then restart HA

### Manual

Copy `custom_components/car_parker/` into your HA `config/custom_components/` directory and restart.

### Configure

Go to **Settings → Devices & Services → Add Integration → Car Parker**.

Enter the URL of your backend, e.g. `http://192.168.1.50:5050`. HA's aiohttp resolver doesn't handle mDNS, so use the IP address rather than a hostname.

---

## Dashboard

A ready-made Lovelace dashboard is in `dashboard/parking.yaml`. It requires the [custom:button-card](https://github.com/custom-cards/button-card) HACS frontend component.

To use it, register the dashboard in `configuration.yaml`:

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

Then copy `dashboard/parking.yaml` to your HA config directory and edit the `entity_id: person.YOUR_NAME` line in the "Park here" button to match your person entity.

---

## Entities

| Entity | Type | Description |
|---|---|---|
| `sensor.car_parker_status` | sensor | `empty` / `pending` / `parked` |
| `sensor.car_parker_urgency` | sensor | `safe` / `soon` / `urgent` / `now` |
| `sensor.next_street_sweep` | timestamp | Next sweep start time |
| `sensor.next_street_sweep_label` | sensor | Human-readable label, e.g. "Tuesday, Jun 3rd 7am–9am" |
| `sensor.parked_location` | sensor | Street + block + side |
| `sensor.parking_time_limit` | sensor | Nearby time-limit restriction (if any) |
| `binary_sensor.car_parked` | binary | On when status is `parked` |
| `binary_sensor.move_car_now` | binary | On when urgency is `urgent` or `now` |
| `binary_sensor.car_parker_needs_side_confirmation` | binary | On during the GPS two-step flow |

---

## Services

| Service | Description |
|---|---|
| `car_parker.park_here` | Capture GPS location (pass `entity_id: person.x` or explicit lat/lng) |
| `car_parker.pick_block` | Choose block from GPS candidates |
| `car_parker.confirm_side` | Confirm which side of the street |
| `car_parker.park_manual` | Set location by free text or street/block/side |
| `car_parker.clear` | Forget the current parking spot |

---

## License

MIT
