# Sleep Apnea Monitor

Digital twin per il rilevamento non invasivo delle apnee notturne. Un dispositivo embedded basato su Arduino monitora il respiro tramite microfono e notifica gli eventi a un backend REST; una simulazione FlexSim replica il sistema su una popolazione virtuale per l'analisi statistica (ROI, falsi positivi/negativi, ottimizzazione delle soglie).

## Architettura

Architettura ad API con un unico database relazionale come fonte di verità.

| Componente | Ruolo |
|---|---|
| Arduino Nano 33 IoT | Rileva le apnee e invia gli eventi via WiFi (HTTP). |
| API FastAPI | Riceve, valida e persiste gli eventi; li espone via REST. |
| Database SQLite | Eventi, pazienti, sessioni, configurazioni e KPI. |
| FlexSim | Digital twin: anima il modello 3D e simula la popolazione di pazienti. |

Flusso dei dati: l'Arduino esegue una `POST` degli eventi all'API, che li scrive nel database; FlexSim legge gli eventi via `GET` per aggiornare il modello e registra i risultati della simulazione tramite l'API.

## Struttura del repository

```
sleep-apnea-monitor/
├── api/                       # API FastAPI e schema del database
│   ├── main.py
│   ├── schema.sql
│   └── requirements.txt
├── arduino_apnea_post/        # Firmware Arduino (rilevamento + invio WiFi)
│   ├── arduino_apnea_post.ino
│   └── arduino_secrets.h      # credenziali WiFi (non versionato)
├── sketchup/                  # Modello 3D dell'ambiente
│   ├── strutturaFissa.skp            # modello SketchUp (ambiente statico)
│   └── strutturaFissa.dae            # esportazione Collada per FlexSim
│   └── ```
└── flexsim/                   # Modello e script FlexSim
    ├── modello.fsm            # modello FlexSim
    └── flexsim_get_events.fs  # script FlexScript
```

> I file binari (`.skp`, `.dae`, `.fsm`) possono essere versionati, ma non si fondono in parallelo: vanno modificati da una persona alla volta (o gestiti con Git LFS se diventano grandi).

## Requisiti

- Python 3.10+
- Arduino IDE con le librerie WiFiNINA e ArduinoHttpClient e il pacchetto Arduino SAMD Boards
- FlexSim con supporto HTTP (v20.1+; v22.1+ consigliata per le POST in JSON)

## Avvio dell'API

```bash
cd api
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Documentazione interattiva su `http://localhost:8000/docs`. Il database `apnea.db` viene creato automaticamente al primo avvio.

## Endpoint

| Metodo | Rotta | Descrizione |
|---|---|---|
| `POST` | `/events` | Registra un evento di apnea o snooze. |
| `GET` | `/events` | Elenca gli eventi (lettura incrementale tramite `since`). |
| `GET` | `/commands` | Comandi di attuazione pendenti per un dispositivo. |
| `POST` | `/responses` | Registra un intervento del personale. |
| `GET` | `/stats` | KPI aggregati (TP/FP/FN, tempi di risposta). |

## Configurazione

- **Arduino** — impostare `SERVER_IP` e `DEVICE_CODE` nello sketch; creare `arduino_secrets.h` con le credenziali WiFi.
- **FlexSim** — impostare l'URL dell'API nello script `flexsim_get_events.fs`.

I file `apnea.db`, `apnea.log` e `arduino_secrets.h` sono esclusi dal versionamento.

## Autori
Daniele Schingaro 
d.schingaro04@gmail.com

Luca Antonio Pistilli
lucapistilli17@gmail.com

Tiberio Sasso
t.sasso3@studenti.uniba.it