# NEXUS

Keyless hotel room proof of concept: an Expo app, a FastAPI backend, an MQTT room simulator and the NORA concierge.

Product and architecture decisions are in [docs/DECISIONS.md](docs/DECISIONS.md).

## Requirements

- Python 3.12 or newer
- Node.js 20.19+ or 22.13+
- Mosquitto (MQTT broker)
- Expo Go on your phone, or an Android/iOS emulator

## One-time setup

From the repository root (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r server/requirements.txt
```

`server/requirements.lock.txt` holds the exact versions in use. To install those instead, use `pip install -r server/requirements.lock.txt`.

Then the app:

```powershell
cd app
npm install
copy .env.example .env.local
```

Open `app/.env.local` and set `EXPO_PUBLIC_API_URL`:

- Emulator or web on the same computer: `http://localhost:8000`
- Physical phone: your computer's LAN address, for example `http://192.168.1.20:8000`. Find it by running `ipconfig` and reading the IPv4 Address. The phone and computer must be on the same Wi-Fi.

## Running

Use four terminals, started in this order. Terminals 2 and 3 need the virtual environment active and must run from the repository root.

1. Broker: if Mosquitto is installed as a Windows service it is already running (check with `Test-NetConnection localhost -Port 1883`). Otherwise run `& "C:\Program Files\mosquitto\mosquitto.exe" -v`
2. Simulator: `python simulator/simulator.py`
3. Backend: `uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload`
4. App: `cd app` then `npx expo start`

Check the backend at http://localhost:8000/health (it should return `{"status":"ok"}`). Interactive API docs are at http://localhost:8000/docs.

The SQLite database `nexus.db` is created in the folder where the backend is started (the repository root). It is ignored by Git. Delete it to start from a clean state.

## Troubleshooting

- **The app shows "connecting..." forever:** the app cannot reach the backend. Check `EXPO_PUBLIC_API_URL`, that the backend was started with `--host 0.0.0.0`, that both devices share a network, and that Windows Firewall allows port 8000. After editing `.env.local`, restart Expo with `npx expo start -c`.
- **The backend fails with a connection error on port 1883:** Mosquitto is not running. Start it first.
- **`mosquitto` is not recognized:** use its full path, for example `& "C:\Program Files\mosquitto\mosquitto.exe" -v`.

## Current limitations

- NORA uses a rules-based fallback. No API key is required.
- Room state is held in memory and resets when the backend restarts.
- Several endpoints (guest lookup, booking list) have no authentication. This is a prototype and must not be exposed publicly.