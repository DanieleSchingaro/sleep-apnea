-- ============================================================
-- Schema SQLite - Sleep Apnea Monitor (digital twin Arduino + FlexSim)
-- Fonte di verita' unica: eventi reali (hardware) e simulati (FlexSim).
-- ============================================================
PRAGMA foreign_keys = ON;

-- Anagrafica fisica -------------------------------------------------
CREATE TABLE IF NOT EXISTS rooms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    device_id   INTEGER
);

CREATE TABLE IF NOT EXISTS devices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,        -- es. "DEV01"
    room_id     INTEGER,
    ip_address  TEXT,
    model       TEXT,
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);

CREATE TABLE IF NOT EXISTS patients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    age         INTEGER,
    bmi         REAL,
    room_id     INTEGER,
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);

-- Configurazioni di taratura (per ottimizzare le soglie) ------------
CREATE TABLE IF NOT EXISTS config_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    drop_ratio          REAL NOT NULL,
    apnea_threshold_sec INTEGER NOT NULL,
    label               TEXT
);

-- Sessioni di monitoraggio ------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  INTEGER,
    device_id   INTEGER,
    config_id   INTEGER,
    start_ts    TEXT,
    end_ts      TEXT,
    origine     TEXT DEFAULT 'hardware',     -- 'hardware' | 'simulazione'
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (device_id)  REFERENCES devices(id),
    FOREIGN KEY (config_id)  REFERENCES config_runs(id)
);

-- Eventi -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS apnea_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER,
    device_code   TEXT NOT NULL,
    ts            TEXT NOT NULL,             -- "YYYY-MM-DD HH:MM:SS"
    threshold_sec INTEGER,
    oscillation   REAL,
    classe        TEXT,                      -- 'TP' | 'FP' | 'FN' | NULL
    source        TEXT DEFAULT 'hardware',   -- 'hardware' | 'simulazione'
    created_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS snooze_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER,
    device_code TEXT NOT NULL,
    ts          TEXT NOT NULL,
    source      TEXT DEFAULT 'hardware',
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Verita' di riferimento (per calcolare TP/FP/FN sugli agenti simulati)
CREATE TABLE IF NOT EXISTS ground_truth (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER,
    ts           TEXT NOT NULL,
    duration_sec INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Risposte del personale (alimentano il calcolo ROI) ----------------
CREATE TABLE IF NOT EXISTS staff_responses (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    apnea_event_id    INTEGER,
    staff_id          INTEGER,
    response_time_sec REAL,
    FOREIGN KEY (apnea_event_id) REFERENCES apnea_events(id)
);

-- Coda comandi di attuazione: l'API accoda, l'Arduino preleva -------
CREATE TABLE IF NOT EXISTS commands (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_code TEXT NOT NULL,
    command     TEXT NOT NULL,               -- es. "ALARM_ON" | "ALARM_OFF"
    created_at  TEXT DEFAULT (datetime('now')),
    consumed    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_apnea_device ON apnea_events(device_code);
CREATE INDEX IF NOT EXISTS idx_cmd_pending  ON commands(device_code, consumed);
