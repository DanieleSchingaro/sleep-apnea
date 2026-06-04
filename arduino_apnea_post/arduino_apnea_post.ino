/*
 * ============================================================
 * Sleep Apnea Monitor - LATO COMUNICAZIONE (Arduino Nano 33 IoT)
 * ------------------------------------------------------------
 * Niente cavo: invia gli eventi APNEA/SNOOZE all'API FastAPI via
 * HTTP POST sulla rete WiFi, e preleva i comandi di attuazione.
 *
 * La logica di RILEVAMENTO (algoritmo a oscillazione gia' calibrato)
 * NON e' qui: si collega tramite gli hook detectApnea() e snoozePressed()
 * in fondo al file. Cosi' chi cura l'Arduino lavora sul rilevamento
 * e questo file resta il "contratto" verso l'API.
 *
 * Librerie (Gestore librerie di Arduino IDE):
 *   - WiFiNINA
 *   - ArduinoHttpClient
 *   - RTClib  (per il DS1307)
 * ============================================================
 */
#include <WiFiNINA.h>
#include <ArduinoHttpClient.h>
#include <Wire.h>
#include <RTClib.h>

// ---- configurazione rete e server ----
const char* WIFI_SSID   = "NOME_RETE";
const char* WIFI_PASS   = "PASSWORD";
const char* SERVER_IP   = "192.168.1.10";   // IP del PC che esegue FastAPI
const int   SERVER_PORT = 8000;
const char* DEVICE_CODE = "DEV01";           // identifica la stanza lato API

// ---- pinout (dal progetto) ----
const int PIN_MIC    = A0;
const int PIN_SNOOZE = 2;    // D2, INPUT_PULLUP, attivo LOW
const int PIN_BUZZER = 3;    // D3
const int PIN_RELAY  = 4;    // D4

const int APNEA_THRESHOLD_SEC = 12;

WiFiClient wifi;
HttpClient http = HttpClient(wifi, SERVER_IP, SERVER_PORT);
RTC_DS1307 rtc;

void connectWiFi() {
  Serial.print("Connessione WiFi");
  while (WiFi.begin(WIFI_SSID, WIFI_PASS) != WL_CONNECTED) {
    Serial.print(".");
    delay(1000);
  }
  Serial.print(" OK - IP: ");
  Serial.println(WiFi.localIP());
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_SNOOZE, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  Wire.begin();
  rtc.begin();
  // se l'RTC non e' mai stato impostato, scommentare per inizializzarlo:
  // rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  connectWiFi();
}

// timestamp "YYYY-MM-DD HH:MM:SS" dal DS1307
String nowString() {
  DateTime n = rtc.now();
  char buf[20];
  sprintf(buf, "%04d-%02d-%02d %02d:%02d:%02d",
          n.year(), n.month(), n.day(), n.hour(), n.minute(), n.second());
  return String(buf);
}

// invia un evento all'API in JSON -> POST /events
void sendEvent(const char* type, int thresholdSec, float oscillation) {
  String body = "{";
  body += "\"type\":\"";        body += type;                      body += "\",";
  body += "\"device_code\":\""; body += DEVICE_CODE;               body += "\",";
  body += "\"ts\":\"";          body += nowString();               body += "\",";
  body += "\"threshold_sec\":"; body += String(thresholdSec);      body += ",";
  body += "\"oscillation\":";   body += String(oscillation, 2);    body += ",";
  body += "\"source\":\"hardware\"";
  body += "}";

  http.post("/events", "application/json", body);
  int status = http.responseStatusCode();
  Serial.print("POST /events ("); Serial.print(type);
  Serial.print(") -> HTTP "); Serial.println(status);
}

// preleva i comandi dall'API -> GET /commands?device=...
void pollCommands() {
  http.get(String("/commands?device=") + DEVICE_CODE);
  int status = http.responseStatusCode();
  if (status != 200) return;
  String resp = http.responseBody();          // es. ["ALARM_ON","ALARM_OFF"]
  if (resp.indexOf("ALARM_ON") >= 0) {
    digitalWrite(PIN_RELAY, HIGH);
  }
  if (resp.indexOf("ALARM_OFF") >= 0) {
    digitalWrite(PIN_RELAY, LOW);
    noTone(PIN_BUZZER);
  }
}

// ===================================================================
// HOOK da collegare al codice di rilevamento gia' calibrato.
// detectApnea(): true quando il silenzio supera APNEA_THRESHOLD_SEC.
// Restituisce anche l'oscillazione corrente (Max-Min) in 'oscOut'.
// ===================================================================
bool detectApnea(float &oscOut) {
  // TODO: inserire qui l'algoritmo a media mobile / DROP_RATIO.
  oscOut = 0.0;
  return false;
}

bool snoozePressed() {
  return digitalRead(PIN_SNOOZE) == LOW;       // attivo LOW (INPUT_PULLUP)
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

  float osc = 0.0;
  if (detectApnea(osc)) {
    tone(PIN_BUZZER, 1000);                     // allarme sonoro locale
    digitalWrite(PIN_RELAY, HIGH);
    sendEvent("APNEA", APNEA_THRESHOLD_SEC, osc);
    delay(1000);
  }

  if (snoozePressed()) {
    noTone(PIN_BUZZER);
    digitalWrite(PIN_RELAY, LOW);
    sendEvent("SNOOZE", 0, 0.0);
    delay(500);                                 // antirimbalzo semplice
  }

  pollCommands();
  delay(200);
}
