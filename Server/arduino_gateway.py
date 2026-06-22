import serial
import time
import requests
import random
import os  # Per gestire la presenza e la cancellazione del file di reset

# ==========================================
# CONFIGURAZIONE SERIALE E PERCORSI
# ==========================================
PORTA_COM = 'COM3' 
BAUD_RATE = 9600
URL_FASTAPI = "http://127.0.0.1:8000/events"

# Percorso del file specchio per spegnere l'allarme
FILE_CLEAR_ALARM = "C:/SC/FlexSim/clear_alarm.txt"

print("====================================================")
print("  GATEWAY BI-DIREZIONALE: HARDWARE <-> FLEXSIM DT   ")
print("====================================================")
print(f"[*] Connessione in corso sulla porta {PORTA_COM}...")

try:
    arduino = serial.Serial()
    arduino.port = PORTA_COM
    arduino.baudrate = BAUD_RATE
    arduino.timeout = 0.1  # Timeout bassissimo per non bloccare i cicli di controllo
    arduino.dtr = False
    arduino.rts = False
    arduino.open()
    time.sleep(2) 
    print("[+] Connessione stabilita con Arduino con successo!")
    print("[*] Gateway pronto e bi-direzionale. (Premi CTRL+C per uscire)")
    print("----------------------------------------------------")
except Exception as e:
    print(f"[-] ERRORE: Impossibile aprire la porta {PORTA_COM}. Chiudi l'IDE di Arduino.")
    print(f"[-] Dettaglio errore: {e}")
    exit()

last_file_check = time.time()

while True:
    try:
        # ──────── MODO 1: ASCOLTO DA ARDUINO (Invio allarmi a FastAPI) ────────
        if arduino.in_waiting > 0:
            linea = arduino.readline().decode('utf-8', errors='ignore').strip()
            if linea:
                print(f"[Hardware Log]: {linea}")
            
            if "GATEWAY_ALERT:" in linea:
                numero_casuale = random.randint(1, 3)
                device_code = f"DEV0{numero_casuale}"
                print(f"\n[🚨 ALLARME INTERCETTATO] Generato stocasticamente: {device_code}!")
                
                payload = {
                    "type": "APNEA",
                    "device_code": device_code,
                    "threshold_sec": 12,
                    "oscillation": 0.0,
                    "source": "hardware",
                    "classe": "TP"
                }
                
                try:
                    response = requests.post(URL_FASTAPI, json=payload)
                    if response.status_code == 200:
                        print(f"[✓] Successo: Evento archiviato nel database per {device_code}.")
                except requests.exceptions.ConnectionError:
                    print("[-] ERRORE DI RETE: Il server FastAPI è spento!\n")

        # ──────── MODO 2: ASCOLTO DA FLEXSIM (Spegnimento Buzzer/LED) ────────
        # Controlliamo la presenza del file ogni 300 millisecondi per massima reattività
        if time.time() - last_file_check >= 0.3:
            last_file_check = time.time()
            
            if os.path.exists(FILE_CLEAR_ALARM):
                print("\n[🔕 MATCH COOPERATIVO] L'infermiere è arrivato nel modello 3D!")
                print("[*] Invio comando di spegnimento seriale ad Arduino...")
                
                # Spediamo il flag di reset sulla seriale con il ritorno a capo obbligatorio
                arduino.write(b"CMD:ALARM_OFF\n")
                
                # Rilasciamo il file eliminandolo, così da essere pronti per il prossimo allarme
                try:
                    os.remove(FILE_CLEAR_ALARM)
                    print("[✓] Coda comandi pulita. Hardware resettato.")
                except Exception as e:
                    print(f"[-] Errore durante la rimozione del file trigger: {e}")

    except KeyboardInterrupt:
        print("\n[*] Rilascio della porta seriale in corso...")
        arduino.close()
        break
    except Exception as e:
        print(f"[-] Errore imprevisto nel loop: {e}")
        time.sleep(1)