# Sleep Apnea Monitor — Architettura ad API (Arduino + FastAPI + FlexSim)

Implementazione dell'architettura richiesta: nessun cavo, tutto via API REST,
un unico database relazionale al centro.

```
Arduino Nano 33 IoT  --WiFi/HTTP-->  FastAPI  <--REST--  FlexSim (digital twin)
        (POST eventi)                  |  ^                (GET eventi, POST risultati)
        (GET comandi) <----------------    |
                                           v
                                   Database SQLite
                              (eventi · pazienti · KPI)
```

## File

| File | Cosa fa |
|---|---|
| `schema.sql` | Schema del database SQLite (tabelle eventi, pazienti, stanze, KPI…). |
| `main.py` | API FastAPI: ingestione eventi, lettura per FlexSim, coda comandi, statistiche. |
| `arduino_apnea_post.ino` | Sketch Nano 33 IoT: connessione WiFi + POST degli eventi all'API. |
| `flexsim_get_events.fs` | Template FlexScript: GET eventi dall'API e accensione della spia. |

## Avvio dell'API

```bash
pip install fastapi "uvicorn[standard]"
uvicorn main:app --host 0.0.0.0 --port 8000
```

- Documentazione interattiva (e test manuale): `http://localhost:8000/docs`
- Il database `apnea.db` viene creato al primo avvio dallo `schema.sql`.
- `--host 0.0.0.0` è necessario perché l'Arduino raggiunga il PC sulla rete.

## Endpoint

| Metodo / rotta | Chi la usa | Scopo |
|---|---|---|
| `POST /events` | Arduino | invia un evento `APNEA` o `SNOOZE` (JSON) |
| `GET /events` | FlexSim / dashboard | eventi di apnea con `id > since` (JSON) |
| `GET /events.csv` | FlexSim | stessi dati in CSV, facili da `split()` |
| `GET /commands?device=` | Arduino | preleva i comandi pendenti (ALARM_ON/OFF) |
| `POST /commands` | API / FlexSim | accoda un comando di attuazione |
| `POST /responses` | FlexSim | registra il tempo di risposta del personale |
| `GET /stats` | dashboard | KPI: totale apnee, TP/FP/FN, snooze, tempo medio |

Esempio di evento inviato dall'Arduino:

```json
{ "type": "APNEA", "device_code": "DEV01",
  "ts": "2026-06-04 23:10:00", "threshold_sec": 12,
  "oscillation": 2.3, "source": "hardware" }
```

## Note di integrazione

- **Identificazione della stanza:** ogni dispositivo ha un `device_code`
  (es. `DEV01`). L'API e FlexSim lo usano per accendere la spia giusta
  (`Spia_DEV01`) e per collegare l'evento alla stanza nel database.

- **FlexSim → API:** FlexSim chiama l'API con la classe `Http.Request`
  (nativa dalla v20.1). Si è scelto l'endpoint **CSV** per evitare il parsing
  JSON in FlexScript. Su versioni FlexSim < 22.1 le POST con `Content-Type:
  application/json` possono dare problemi (default `x-www-form-urlencoded`):
  per questo FlexSim qui fa soprattutto **GET**.

- **Hardware vs simulazione:** il campo `source` distingue gli eventi reali
  (`hardware`, dall'Arduino) da quelli dei 200+ agenti (`simulazione`,
  generati da FlexSim e inviati con lo stesso `POST /events`). Stesso schema,
  stesse query: filtri per `source` quando vuoi confrontarli.

- **Falsi positivi/negativi:** la tabella `ground_truth` contiene le apnee
  "vere" degli agenti simulati; confrontandola con `apnea_events` classifichi
  ogni evento (`classe` = TP/FP/FN) e calcoli i KPI in `GET /stats`.

- **Tracciamento (`apnea.log`):** ogni evento, comando e risposta viene
  scritto anche in `apnea.log` (in chiaro, con orario), oltre che nel database.
  Comodo per ricostruire la cronologia o allegare un log alla relazione.

- **Git:** `apnea.db` e `apnea.log` sono generati a runtime e NON vanno
  versionati (sono già nel `.gitignore`). Si versionano solo i sorgenti.

