"""
============================================================
Script di Sync - Ponte tra FastAPI e FlexSim 2019
============================================================
"""
import time
import requests
import os

# ==========================================
# CONFIGURAZIONE
# ==========================================
# ⚠️ CAMBIA QUESTO PERCORSO con la cartella reale del tuo modello FlexSim!
MODEL_DIR = r"C:\SC\FlexSim"

# Indirizzo del server FastAPI
SERVER_URL = "http://localhost:8000"

# Intervallo di polling in secondi
POLL_INTERVAL = 10


def main():
    print("🔄 Script di Sync avviato...")
    print(f"📁 Cartella modello FlexSim: {MODEL_DIR}")
    print(f"🌐 Server URL: {SERVER_URL}")
    print("-" * 50)

    # Crea la cartella se non esiste
    os.makedirs(MODEL_DIR, exist_ok=True)

    while True:
        try:
            # 1️⃣ AGGIORNAMENTO CSV PER FLEXSIM
            try:
                requests.get(f"{SERVER_URL}/export_csv", timeout=5)
            except requests.exceptions.RequestException:
                # Il server non è ancora pronto, ignoriamo silenziosamente
                pass

            # 2️⃣ LETTURA RISPOSTA DA FLEXSIM
            response_file = os.path.join(MODEL_DIR, "response.txt")
            
            if os.path.exists(response_file):
                try:
                    # Rinominiamo temporaneamente il file per "strapparlo" dalle mani di FlexSim
                    # Se FlexSim lo sta ancora scrivendo, questo solleverà un PermissionError gestito dal try
                    temp_file = response_file + ".tmp"
                    os.rename(response_file, temp_file)
                    
                    # Ora leggiamo il file temporaneo in sicurezza riga per riga
                    with open(temp_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue  # Salta righe vuote
                        
                        # Separazione corretta per singola riga
                        parts = line.split("|")
                        if len(parts) >= 2:
                            try:
                                event_id = int(parts[0])
                                response_time = float(parts[1])
                                
                                # Invia i dati al server FastAPI
                                url_import = f"{SERVER_URL}/import_response?event_id={event_id}&response_time={response_time}"
                                requests.post(url_import, timeout=5)
                                
                                print(f"✅ Risposta salvata nel DB: Evento ID {event_id} | Tempo: {response_time}s")
                            except ValueError:
                                print(f"⚠️ Riga malformata nel file di risposta: '{line}'")
                            except requests.exceptions.RequestException as e:
                                print(f"❌ Errore di rete nell'invio della risposta {event_id}: {e}")
                    
                    # Rimosso il file temporaneo dopo aver elaborato tutte le righe
                    os.remove(temp_file)
                    
                except PermissionError:
                    # FlexSim sta ancora scrivendo nel file, ci riproviamo al prossimo ciclo
                    pass
                except Exception as e:
                    print(f"⚠️ Errore durante l'elaborazione di response.txt: {e}")

        except Exception as e:
            print(f"❌ Errore generale nel loop di sync: {e}")

        # Pausa prima del prossimo controllo
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()