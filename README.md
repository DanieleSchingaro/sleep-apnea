# Sleep Apnea Monitor — APNEASENSE IoT

A digital twin for non-invasive detection of nocturnal sleep apnea. An embedded device based on the Arduino Nano 33 IoT monitors breathing through a microphone and reports events to a REST backend (FastAPI); a FlexSim simulation mirrors the system over a virtual patient population for statistical analysis (ROI, false positives/negatives, threshold tuning).

## Architecture

API-based system with a single relational database (SQLite) as the source of truth. Communication between the Arduino and the PC happens **over USB serial**: a Python gateway translates serial messages into HTTP calls to the API.

| Component | Role |
|---|---|
| Arduino Nano 33 IoT | Detects apnea from the microphone and emits events over the USB serial port; receives reset commands. |
| `arduino_gateway.py` | Serial <-> HTTP bridge: reads the serial port and forwards events to the API (`POST /events`); relays shutdown commands back to the Arduino. |
| FastAPI service (`main.py`) | Receives, validates and persists events; exposes the REST endpoints; writes `live_alarm.txt` into the FlexSim folder. |
| SQLite database | Events, patients, sessions, configurations and KPIs. |
| `sync_simple.py` | Synchronization: reads the `response.txt` produced by FlexSim and pushes response times back via `POST /import_response`. |
| FlexSim 2019 | Digital twin: reads `live_alarm.txt`, animates the 3D model and writes the intervention times. |

Data flow: Arduino -> (USB serial) -> `arduino_gateway.py` -> `POST /events` -> `main.py` (SQLite + `live_alarm.txt`) -> FlexSim reacts -> `response.txt` -> `sync_simple.py` -> `POST /import_response` -> SQLite.

## Repository structure

```
SLEEP-APNEA/
├── DAE_components               # 3D models (Collada) imported into FlexSim
│   ├── comodino.dae
│   ├── letto.dae
│   ├── parabolaAcustica.dae
│   ├── scatola.dae
│   └── struttura.dae
├── Flexsim/                     # FlexSim model and exchange files
│   ├── API_Collegate.fsm        # FlexSim model (versioned)
│   ├── events.csv               # generated at runtime
│   └── live_alarm.txt           # generated at runtime
├── Server/                      # Python backend
│   ├── main.py                  # FastAPI API + SQLite access
│   ├── schema.sql               # database schema
│   ├── arduino_gateway.py       # USB serial <-> HTTP bridge
│   ├── sync_simple.py           # FlexSim <-> API synchronization
│   ├── apnea.db                 # database (generated at runtime)
│   └── apnea.log                # log (generated at runtime)
├── .gitignore
├── README.md
└── requirements.txt
```

> The binary files (`.fsm`, `.dae`) are versioned but cannot be merged in parallel: edit them one person at a time (or manage them with Git LFS if they grow large). The files `apnea.db`, `apnea.log`, `events.csv`, `live_alarm.txt` and `response.txt` are generated at runtime and excluded from version control.

## Requirements

- Python 3.10+
- Python dependencies in `requirements.txt`: FastAPI, Uvicorn, Requests, PySerial
- Arduino IDE with the **Arduino SAMD Boards** package (for the Nano 33 IoT)
- FlexSim 2019 (the model exchanges data via files, so it does not require native HTTP support)

## Running the system

Install the dependencies (from the repository root):

```bash
pip install -r requirements.txt
```

Three processes must be running, each in its own terminal:

```bash
# 1) FastAPI API
cd Server
uvicorn main:app --host 0.0.0.0 --port 8000

# 2) FlexSim -> DB synchronization
cd Server
python sync_simple.py

# 3) Arduino <-> API serial gateway (with the Arduino connected via USB)
cd Server
python arduino_gateway.py
```

Then open `flexsim/API_Collegate.fsm` in FlexSim, press **Reset** and **Run**.

Interactive API docs at `http://localhost:8000/docs`. The `apnea.db` database is created automatically on the API's first start.

## Endpoints

| Method | Route | Description |
|---|---|---|
| `POST` | `/events` | Records an apnea or snooze event; writes `live_alarm.txt` for FlexSim. |
| `GET` | `/events` | Lists events (incremental read via `since`). |
| `GET` | `/events.csv` | Events in CSV format. |
| `GET` | `/commands` | Pending actuation commands for a device. |
| `POST` | `/commands` | Queues a command for a device. |
| `POST` | `/responses` | Records a staff intervention. |
| `GET` | `/stats` | Aggregated KPIs (TP/FP/FN, response times). |
| `GET` | `/export_csv` | [Legacy] Writes `events.csv` into the FlexSim folder. |
| `POST` | `/import_response` | Pushes the response times read from FlexSim back into the DB. |

## Configuration

- **`arduino_gateway.py`** — set the Arduino serial port (e.g. `COM3`), the baud rate (`9600`) and the API URL (`SERVER_URL`).
- **`sync_simple.py`** — set `MODEL_DIR` to the `flexsim/` folder (where the `.fsm` lives) and the API URL.
- **`main.py`** — `MODEL_DIR` points to the FlexSim model folder; make sure the folder name matches the real one (`flexsim`), especially on case-sensitive systems.

The files `apnea.db`, `apnea.log`, `events.csv` and `live_alarm.txt` are excluded from version control.

## Authors

- Daniele Schingaro — d.schingaro04@gmail.com
- Luca Antonio Pistilli — lucapistilli17@gmail.com
- Tiberio Sasso — t.sasso3@studenti.uniba.it