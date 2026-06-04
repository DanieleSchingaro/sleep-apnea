"""
============================================================
API FastAPI - Sleep Apnea Monitor (digital twin Arduino + FlexSim)
------------------------------------------------------------
Ruolo: e' l'"ingranaggio API" centrale dell'architettura.
 - L'Arduino Nano 33 IoT (WiFi) fa POST /events  -> ingestione
 - FlexSim fa GET /events (o /events.csv)        -> legge per animare il twin
 - L'Arduino fa GET /commands                    -> preleva comandi attuazione
 - FlexSim fa POST /responses                    -> registra tempi del personale
 - Le dashboard fanno GET /stats                 -> KPI (ROI, falsi pos/neg)
Persistenza: un unico database relazionale SQLite (apnea.db).

Avvio:
    pip install fastapi "uvicorn[standard]"
    uvicorn main:app --host 0.0.0.0 --port 8000
Doc interattiva: http://localhost:8000/docs
============================================================
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

DB_PATH = Path(__file__).parent / "apnea.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
LOG_PATH = Path(__file__).parent / "apnea.log"

# ---------- logging: traccia tutto su file (e su console) ----------
log = logging.getLogger("apnea")
log.setLevel(logging.INFO)
log.propagate = False  # non ereditare i log di librerie terze (httpx, uvicorn)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_file = logging.FileHandler(LOG_PATH, encoding="utf-8")
_file.setFormatter(_fmt)
_console = logging.StreamHandler()
_console.setFormatter(_fmt)
if not log.handlers:                 # evita handler duplicati ai reload
    log.addHandler(_file)
    log.addHandler(_console)

app = FastAPI(title="Sleep Apnea Monitor API", version="1.0")


# ---------- accesso al database ----------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Crea le tabelle dallo schema se non esistono (idempotente)."""
    conn = get_conn()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


# inizializza subito: garantisce le tabelle sia con `uvicorn main:app`
# sia importando il modulo (test, script).
init_db()


# ---------- modelli (validazione automatica del JSON in ingresso) ----------
class EventIn(BaseModel):
    type: str                          # "APNEA" | "SNOOZE"
    device_code: str                   # es. "DEV01"
    ts: Optional[str] = None           # se assente, lo mette il server (device senza RTC)
    threshold_sec: Optional[int] = None
    oscillation: Optional[float] = None
    source: str = "hardware"           # "hardware" | "simulazione"


class ResponseIn(BaseModel):
    apnea_event_id: int
    staff_id: Optional[int] = None
    response_time_sec: float


class CommandIn(BaseModel):
    device_code: str
    command: str


# ---------- ingestione eventi (Arduino -> API) ----------
@app.post("/events")
def post_event(ev: EventIn):
    t = ev.type.upper()
    ts = ev.ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # orario lato server se assente
    conn = get_conn()
    cur = conn.cursor()
    if t == "APNEA":
        cur.execute(
            "INSERT INTO apnea_events (device_code, ts, threshold_sec, oscillation, source) "
            "VALUES (?,?,?,?,?)",
            (ev.device_code, ts, ev.threshold_sec, ev.oscillation, ev.source),
        )
        event_id = cur.lastrowid
        cur.execute("INSERT INTO commands (device_code, command) VALUES (?, 'ALARM_ON')",
                    (ev.device_code,))
        conn.commit(); conn.close()
        log.info("APNEA  device=%s ts=%s soglia=%ss osc=%s source=%s (id=%s)",
                 ev.device_code, ts, ev.threshold_sec, ev.oscillation, ev.source, event_id)
        return {"status": "ok", "type": "APNEA", "id": event_id}

    if t in ("SNOOZE", "SNOOZE_ACTIVATED"):
        cur.execute("INSERT INTO snooze_events (device_code, ts, source) VALUES (?,?,?)",
                    (ev.device_code, ts, ev.source))
        event_id = cur.lastrowid
        cur.execute("INSERT INTO commands (device_code, command) VALUES (?, 'ALARM_OFF')",
                    (ev.device_code,))
        conn.commit(); conn.close()
        log.info("SNOOZE device=%s ts=%s source=%s (id=%s)",
                 ev.device_code, ts, ev.source, event_id)
        return {"status": "ok", "type": "SNOOZE", "id": event_id}

    conn.close()
    log.warning("evento di tipo sconosciuto rifiutato: %s (device=%s)", ev.type, ev.device_code)
    raise HTTPException(status_code=400, detail=f"tipo evento sconosciuto: {ev.type}")


# ---------- lettura eventi (FlexSim / dashboard -> API) ----------
@app.get("/events")
def get_events(since: int = 0, device: Optional[str] = None, limit: int = 100):
    """Restituisce gli eventi di apnea con id > 'since' (lettura incrementale)."""
    conn = get_conn()
    q = ("SELECT id, device_code, ts, threshold_sec, oscillation, classe, source "
         "FROM apnea_events WHERE id > ?")
    params = [since]
    if device:
        q += " AND device_code = ?"; params.append(device)
    q += " ORDER BY id ASC LIMIT ?"; params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/events.csv", response_class=PlainTextResponse)
def get_events_csv(since: int = 0, device: Optional[str] = None, limit: int = 100):
    """Stessa lista in CSV: comoda da parsare in FlexSim con string.split().
    Formato riga: id,device_code,ts,threshold_sec"""
    rows = get_events(since=since, device=device, limit=limit)
    lines = []
    for r in rows:
        thr = r["threshold_sec"] if r["threshold_sec"] is not None else ""
        lines.append(f'{r["id"]},{r["device_code"]},{r["ts"]},{thr}')
    return "\n".join(lines)


# ---------- comandi di attuazione (Arduino preleva) ----------
@app.get("/commands")
def get_commands(device: str):
    """Ritorna i comandi pendenti per il dispositivo e li marca come consumati."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, command FROM commands WHERE device_code = ? AND consumed = 0 ORDER BY id ASC",
        (device,),
    ).fetchall()
    ids = [r["id"] for r in rows]
    if ids:
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"UPDATE commands SET consumed = 1 WHERE id IN ({placeholders})", ids)
        conn.commit()
        log.info("comandi consegnati a %s: %s", device, [r["command"] for r in rows])
    conn.close()
    return [r["command"] for r in rows]


@app.post("/commands")
def post_command(cmd: CommandIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO commands (device_code, command) VALUES (?,?)",
                (cmd.device_code, cmd.command))
    cid = cur.lastrowid
    conn.commit(); conn.close()
    return {"status": "ok", "id": cid}


# ---------- risposte del personale (FlexSim -> API) ----------
@app.post("/responses")
def post_response(r: ResponseIn):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO staff_responses (apnea_event_id, staff_id, response_time_sec) VALUES (?,?,?)",
        (r.apnea_event_id, r.staff_id, r.response_time_sec),
    )
    rid = cur.lastrowid
    conn.commit(); conn.close()
    log.info("risposta personale: evento=%s staff=%s tempo=%ss (id=%s)",
             r.apnea_event_id, r.staff_id, r.response_time_sec, rid)
    return {"status": "ok", "id": rid}


# ---------- statistiche / KPI ----------
@app.get("/stats")
def get_stats(device: Optional[str] = None):
    conn = get_conn()
    where = " WHERE device_code = ?" if device else ""
    params = (device,) if device else ()
    row = conn.execute(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN classe='TP' THEN 1 ELSE 0 END) AS tp,
               SUM(CASE WHEN classe='FP' THEN 1 ELSE 0 END) AS fp,
               SUM(CASE WHEN classe='FN' THEN 1 ELSE 0 END) AS fn
        FROM apnea_events{where}
    """, params).fetchone()
    snooze = conn.execute(f"SELECT COUNT(*) FROM snooze_events{where}", params).fetchone()[0]
    avg_resp = conn.execute("SELECT AVG(response_time_sec) FROM staff_responses").fetchone()[0]
    conn.close()
    return {
        "apnea_total": row["total"] or 0,
        "TP": row["tp"] or 0, "FP": row["fp"] or 0, "FN": row["fn"] or 0,
        "snooze_total": snooze,
        "avg_response_sec": avg_resp,
    }
