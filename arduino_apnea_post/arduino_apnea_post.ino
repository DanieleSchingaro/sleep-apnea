/*
 * ============================================================
 * Sleep Apnea Monitor - Nano 33 IoT (RILEVAMENTO + INVIO WiFi)
 * ------------------------------------------------------------
 * Algoritmo di rilevamento: invariato rispetto al codice base.
 * Aggiunto: connessione WiFi e POST /events all'API FastAPI
 *   - APNEA  quando scatta l'allarme
 *   - SNOOZE quando il pulsante resetta un allarme attivo
 * Le credenziali WiFi stanno in arduino_secrets.h (NON versionato).
 *
 * Librerie: WiFiNINA, ArduinoHttpClient
 * ============================================================
 */
#include <WiFiNINA.h>
#include <ArduinoHttpClient.h>
#include "arduino_secrets.h"

// --- CONFIGURAZIONE RETE / API ---
const char* WIFI_SSID   = SECRET_SSID;     // da arduino_secrets.h
const char* WIFI_PASS   = SECRET_PASS;     // da arduino_secrets.h
const char* SERVER_IP   = "192.168.1.10";  // IP del PC che esegue FastAPI
const int   SERVER_PORT = 8000;
const char* DEVICE_CODE = "DEV01";         // identifica la stanza lato API

WiFiClient wifi;
HttpClient http = HttpClient(wifi, SERVER_IP, SERVER_PORT);

// --- CONFIGURAZIONE PIN ---
const int pinAnalogico = A0;  // Output Analogico del modulo Big Sound
const int pinButton = 2;     // Pulsante di Stop/Reset Allarme (collegato a GND)
const int pinBuzzer = 3;     // Pin dedicato al Buzzer
const int pinLEDRosso = 8;   // LED Rosso classico a due piedini collegato al Pin D8

// --- COSTANTI DI TEMPO ---
const unsigned long INTERVALLO = 250; // Finestra di campionamento microfono (250ms)
const int SOGLIA_APNEA_SECONDI = 12;  // Secondi di silenzio prima dell'allarme

// --- SOGLIA DI SILENZIO RICHIESTA ---
const int SOGLIA_SILENZIO = 30; 

// --- VARIABILI DI STATO ---
unsigned long ultimoRespiroMillis = 0; 
bool inAllarme = false;
unsigned long lastBuzzerToggle = 0;
bool buzzerState = false;

// --- WiFi: connessione (richiamata anche se cade) ---
void connectWiFi() {
  Serial.print("Connessione WiFi");
  while (WiFi.begin(WIFI_SSID, WIFI_PASS) != WL_CONNECTED) {
    Serial.print(".");
    delay(1000);
  }
  Serial.print(" OK - IP: ");
  Serial.println(WiFi.localIP());
}

// --- Invio evento all'API: POST /events (l'orario lo mette il server) ---
void sendEvent(const char* type, int thresholdSec, int oscillazione) {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  String body = "{";
  body += "\"type\":\"";        body += type;                  body += "\",";
  body += "\"device_code\":\""; body += DEVICE_CODE;           body += "\",";
  body += "\"threshold_sec\":"; body += String(thresholdSec);  body += ",";
  body += "\"oscillation\":";   body += String(oscillazione);
  body += "}";

  http.post("/events", "application/json", body);
  int status = http.responseStatusCode();
  Serial.print("POST /events ("); Serial.print(type);
  Serial.print(") -> HTTP "); Serial.println(status);
}

void setup() {
  // Configurazione hardware dei pin
  pinMode(pinButton, INPUT_PULLUP); 
  pinMode(pinBuzzer, OUTPUT);
  pinMode(pinLEDRosso, OUTPUT);   
  
  // STATO INIZIALE DI SICUREZZA: Tutto spento all'avvio
  digitalWrite(pinBuzzer, LOW);
  noTone(pinBuzzer);
  digitalWrite(pinLEDRosso, LOW); 

  // Inizializziamo la comunicazione seriale (solo debug via USB)
  Serial.begin(9600);
  Serial.println("--- SISTEMA ANTI-APNEA: MEMORIA D'ALLARME ATTIVA ---");

  // Connessione alla rete WiFi
  connectWiFi();
  
  // Fissiamo il punto di partenza del cronometro all'avvio
  ultimoRespiroMillis = millis(); 
}

void loop() {
  // 1. GESTIONE PULSANTE DI RESET (L'unico modo per spegnere l'allarme)
  if (digitalRead(pinButton) == LOW) {
    bool eraInAllarme = inAllarme;          // memorizza se stava suonando
    inAllarme = false;
    digitalWrite(pinBuzzer, LOW);
    noTone(pinBuzzer);
    digitalWrite(pinLEDRosso, LOW); // Spegne subito il LED rosso
    
    // Azzeriamo il cronometro facendolo ripartire da questo istante
    ultimoRespiroMillis = millis(); 
    
    Serial.println("-> RESET EFFETTUATO CON IL PULSANTE. Ripristino monitoraggio. <-");

    // Notifica SNOOZE all'API solo se stava effettivamente suonando
    if (eraInAllarme) sendEvent("SNOOZE", 0, 0);

    delay(300); // Ritardo anti-rimbalzo
  }

  // 2. CAMPIONAMENTO DEL MICROFONO (Eseguito solo se NON siamo già in allarme)
  int oscillazione = 0;
  
  if (!inAllarme) {
    int maxVal = 0;
    int minVal = 1023;
    unsigned long startTime = millis();

    while (millis() - startTime < INTERVALLO) {
      int lettore = analogRead(pinAnalogico);
      if (lettore > maxVal) maxVal = lettore;
      if (lettore < minVal) minVal = lettore;
    }

    oscillazione = maxVal - minVal;

    // 3. CONTROLLO SOGLIA RUMORE (Se > 30 resetta il timer del silenzio)
    if (oscillazione > SOGLIA_SILENZIO) {
      ultimoRespiroMillis = millis(); 
    }

    // 4. CALCOLO REALE DEI SECONDI TRASCORSI
    unsigned long tempoPassatoMillis = millis() - ultimoRespiroMillis;
    int secondiSenzaRumore = tempoPassatoMillis / 1000; 

    // 5. LOGICA DI MONITORAGGIO SULLA SERIALE
    digitalWrite(pinLEDRosso, LOW); // Garantisce che rimanga spento durante il monitoraggio
    
    Serial.print("Oscillazione: ");
    Serial.print(oscillazione);
    Serial.print(" | Tempo di Silenzio: ");
    Serial.print(secondiSenzaRumore);
    Serial.print("s / ");
    Serial.print(SOGLIA_APNEA_SECONDI);
    Serial.println("s");

    // 6. CONTROLLO SCADENZA DEI 12 SECONDI
    if (secondiSenzaRumore >= SOGLIA_APNEA_SECONDI) {
      inAllarme = true;
      Serial.println("!!! ATTENZIONE: ALLARME APNEA SCATTATO !!!");

      // Notifica APNEA all'API
      sendEvent("APNEA", SOGLIA_APNEA_SECONDI, oscillazione);
    }
  }

  // 7. GESTIONE ALLARME COORDINATO (Buzzer + LED Rosso a intermittenza bloccata)
  if (inAllarme) {
    if (millis() - lastBuzzerToggle >= 250) { 
      buzzerState = !buzzerState;
      if (buzzerState) {
        digitalWrite(pinBuzzer, HIGH); 
        tone(pinBuzzer, 1000); 
        digitalWrite(pinLEDRosso, HIGH); // Accende il LED rosso
      } else {
        digitalWrite(pinBuzzer, LOW);
        noTone(pinBuzzer);
        digitalWrite(pinLEDRosso, LOW);  // Spegne il LED rosso
      }
      lastBuzzerToggle = millis();
    }
  }
}
