/* ============================================================
   FlexScript - LETTURA EVENTI DALL'API E ACCENSIONE SPIE
   ------------------------------------------------------------
   Da eseguire periodicamente (es. trigger temporale ogni 1 s,
   oppure un blocco in Process Flow con un Delay in loop).
   Richiede FlexSim >= 20.1 (classe Http.Request).

   ATTENZIONE: questo e' un TEMPLATE da adattare alla tua versione
   di FlexSim. L'esatta firma di Http.Request (invio sincrono vs
   callback) e i metodi delle stringhe cambiano tra versioni:
   vedi docs.flexsim.com -> FlexScript API Reference -> Http.Request.
   Si usa l'endpoint CSV (/events.csv) perche' e' banale da parsare
   con split(), senza bisogno di un parser JSON.
   ============================================================ */

// --- id dell'ultimo evento gia' elaborato, salvato in una label del Model ---
treenode tools = Model.find("Tools");
if (!tools.labels.exists("lastEventId"))
    tools.labels.assert("lastEventId", 0);
int lastId = tools.labels["lastEventId"].value;

// --- costruisci l'URL incrementale ---
string url = "http://192.168.1.10:8000/events.csv?since=" + numtostring(lastId, 0, 0);

// --- invia la richiesta GET (adatta send/callback alla tua versione) ---
Http.Request req = Http.Request(url);
Http.Response resp = req.send();

if (resp.statusCode == 200 && resp.data != "") {
    // ogni riga: id,device_code,ts,threshold
    Array righe = resp.data.split("\n");
    for (int i = 1; i <= righe.length; i++) {
        string riga = righe[i];
        if (riga == "") continue;

        Array campi   = riga.split(",");
        int    id     = stringtonum(campi[1]);
        string device = campi[2];

        // accendi la spia associata al dispositivo (named "Spia_DEV01", ...)
        treenode spia = Model.find("Spia_" + device);
        if (spia != NULL)
            spia.color = Color.red;

        // QUI puoi anche: far partire il personale verso quella stanza,
        // e poi fare POST /responses con il tempo di risposta misurato.

        if (id > lastId) lastId = id;
    }
    tools.labels["lastEventId"].value = lastId;
}
