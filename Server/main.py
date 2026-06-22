"""
============================================================
API FastAPI - Sleep Apnea Monitor (digital twin Arduino + FlexSim)
============================================================
"""
import logging
import sqlite3
import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

# ==========================================
# CONFIGURAZIONE PERCORSI (Gestione robusta e coerente)
# ==========================================
DB_PATH = Path(__file__).parent / "apnea.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
LOG_PATH = Path(__file__).parent / "apnea.log"

# 🎯 SOLUZIONE PERCORSI: Saliamo di un livello per entrare in 'FlexSim'
MODEL_DIR = Path(__file__).parent.parent / "FlexSim"

# 🚀 NUOVO PERCORSO MONORIGA: File txt nudo per bypassare i bug di FlexSim 2019
TXT_PATH = MODEL_DIR / "live_alarm.txt"

# ==========================================
# LOGGING
# ==========================================
log = logging.getLogger("apnea")
log.setLevel(logging.INFO)
log.propagate = False
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_file = logging.FileHandler(LOG_PATH, encoding="utf-8")
_file.setFormatter(_fmt)
_console = logging.StreamHandler()
_console.setFormatter(_fmt)
if not log.handlers:
    log.addHandler(_file)
    log.addHandler(_console)

app = FastAPI(title="Sleep Apnea Monitor API", version="1.0")


# ==========================================
# DATABASE
# ==========================================
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF") 
    return conn

def init_db():
    """Crea le tabelle dallo schema se non esistono (idempotente)."""
    if not SCHEMA_PATH.exists():
        log.warning("schema.sql non trovato, salto inizializzazione tabelle.")
        return
    conn = get_conn()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()

# Inizializza il DB all'avvio
init_db()


# ==========================================
# MODELLI PYDANTIC (Validazione JSON)
# ==========================================
class EventIn(BaseModel):
    type: str                          # "APNEA" | "SNOOZE"
    device_code: str                   # es. "DEV01"
    ts: Optional[str] = None           # se assente, lo mette il server
    threshold_sec: Optional[int] = None
    oscillation: Optional[float] = None
    source: str = "hardware"           # "hardware" | "simulazione"
    classe: Optional[str] = "TP"       # Default a True Positive per la simulazione

class ResponseIn(BaseModel):
    apnea_event_id: int
    staff_id: Optional[int] = None
    response_time_sec: float

class CommandIn(BaseModel):
    device_code: str
    command: str


# ==========================================
# ENDPOINT ORIGINALI MODIFICATI (Arduino / Dashboard)
# ==========================================

@app.post("/events")
def post_event(ev: EventIn):
    t = ev.type.upper()
    ts = ev.ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("INSERT OR IGNORE INTO devices (code) VALUES (?)", (ev.device_code,))

    if t == "APNEA":
        cur.execute(
            "INSERT INTO apnea_events (device_code, ts, threshold_sec, oscillation, source, classe) "
            "VALUES (?,?,?,?,?,?)",
            (ev.device_code, ts, ev.threshold_sec, ev.oscillation, ev.source, ev.classe),
        )
        event_id = cur.lastrowid
        cur.execute("INSERT INTO commands (device_code, command) VALUES (?, 'ALARM_ON')",
                    (ev.device_code,))
        conn.commit()
        conn.close()
        
        # 🎯 MAPPAZIONE DINAMICA DELL'ANZIANO basata sul device_code
        device = ev.device_code
        # Mappatura pulita per tutti e tre i dispositivi
        if "DEV01" in device:
            anziano_id = 1
        elif "DEV02" in device:
            anziano_id = 2
        elif "DEV03" in device:
            anziano_id = 3
        else:
            anziano_id = 1 # Fallback di sicurezza
        
        # 🚀 APERTURA E AGGIORNAMENTO CHIRURGICO DEL FILE MONORIGA PER FLEXSIM
        # Usiamo retry per evitare PermissionError nel caso sfortunatissimo in cui stiano scrivendo e leggendo nello stesso istante.
        for _ in range(5):
            try:
                MODEL_DIR.mkdir(parents=True, exist_ok=True)
                # encoding="ascii" ed end="" rimuovono all'origine il BOM e il newline (\n)
                with open(TXT_PATH, "w", encoding="ascii") as f:
                    f.write(f"{event_id} {anziano_id}")
                break
            except PermissionError:
                time.sleep(0.05)

        log.info("APNEA device=%s ts=%s soglia=%ss osc=%s source=%s (id=%s) -> TXT FlexSim scritto.",
                 ev.device_code, ts, ev.threshold_sec, ev.oscillation, ev.source, event_id)
        return {"status": "ok", "type": "APNEA", "id": event_id}

    if t in ("SNOOZE", "SNOOZE_ACTIVATED"):
        cur.execute("INSERT INTO snooze_events (device_code, ts, source) VALUES (?,?,?)",
                    (ev.device_code, ts, ev.source))
        event_id = cur.lastrowid
        cur.execute("INSERT INTO commands (device_code, command) VALUES (?, 'ALARM_OFF')",
                    (ev.device_code,))
        conn.commit()
        conn.close()
        log.info("SNOOZE device=%s ts=%s source=%s (id=%s)",
                 ev.device_code, ts, ev.source, event_id)
        return {"status": "ok", "type": "SNOOZE", "id": event_id}

    conn.close()
    log.warning("evento di tipo sconosciuto rifiutato: %s (device=%s)", ev.type, ev.device_code)
    raise HTTPException(status_code=400, detail=f"tipo evento sconosciuto: {ev.type}")


@app.get("/events")
def get_events(since: int = 0, device: Optional[str] = None, limit: int = 100):
    conn = get_conn()
    q = ("SELECT id, device_code, ts, threshold_sec, oscillation, IFNULL(classe, 'TP') as classe, source "
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
    rows = get_events(since=since, device=device, limit=limit)
    lines = ["id;device_code;ts;classe"]
    for r in rows:
        lines.append(f'{r["id"]};{r["device_code"]};{r["ts"]};{r["classe"]}')
    return "\n".join(lines)


@app.get("/commands")
def get_commands(device: str):
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


@app.get("/stats")
def get_stats(device: Optional[str] = None):
    conn = get_conn()
    where = " WHERE device_code = ?" if device else ""
    params = (device,) if device else ()
    row = conn.execute(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN IFNULL(classe, 'TP')='TP' THEN 1 ELSE 0 END) AS tp,
               SUM(CASE WHEN IFNULL(classe, 'TP')='FP' THEN 1 ELSE 0 END) AS fp,
               SUM(CASE WHEN IFNULL(classe, 'TP')='FN' THEN 1 ELSE 0 END) AS fn
        FROM apnea_events{where}
    """, params).fetchone()
    snooze = conn.execute(f"SELECT COUNT(*) FROM snooze_events{where}", params).fetchone()[0]
    avg_resp = conn.execute("SELECT AVG(response_time_sec) FROM staff_responses").fetchone()[0]
    conn.close()
    return {
        "apnea_total": row["total"] or 0,
        "TP": row["tp"] or 0, "FP": row["fp"] or 0, "FN": row["fn"] or 0,
        "snooze_total": snooze,
        "avg_response_sec": avg_resp or 0.0,
    }


# ==========================================
# PONTE PER FLEXSIM 2019 LEGACY (Mantenuto per retrocompatibilità)
# ==========================================
@app.get("/export_csv")
def export_csv():
    csv_path = MODEL_DIR / "events.csv"
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM (
            SELECT id, device_code, IFNULL(classe, 'TP') as classe 
            FROM apnea_events 
            ORDER BY id DESC LIMIT 100
        ) ORDER BY id ASC
    """).fetchall()
    conn.close()
    
    for tentativo in range(5):
        try:
            with open(csv_path, "w", newline="\n", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["id", "device_code", "classe", "anziano"])
                if not rows:
                    writer.writerow([0, "DEV00", "TP", 0])
                else:
                    for r in rows:
                        device = r["device_code"]
                        anziano_id = 1 if "DEV01" in device else (2 if "DEV02" in device else 1)
                        writer.writerow([r["id"], device, r["classe"], anziano_id])
            return {"status": "ok", "file": str(csv_path)}
        except PermissionError:
            time.sleep(0.1)
            continue
    raise HTTPException(status_code=500, detail="File bloccato da FlexSim.")


@app.post("/import_response")
def import_response(event_id: int, response_time: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO staff_responses (apnea_event_id, staff_id, response_time_sec) VALUES (?,?,?)",
        (event_id, 1, response_time)
    )
    conn.commit()
    conn.close()
    log.info("Risposta importata da FlexSim: evento=%s tempo=%ss", event_id, response_time)
    return {"status": "ok"}