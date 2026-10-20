#include <Arduino.h>
#include <WiFi.h>
#include <time.h>

#include "config.h"
#include "secrets.h"
#include "flow_sensor.h"
#include "telemetry_client.h"

namespace {

FlowSensor flowSensor;
TelemetryClient telemetryClient;
unsigned long lastSampleAt = 0;

void connectWiFi() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.printf("Conectando ao WiFi \"%s\"", WIFI_SSID);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\nWiFi conectado, IP %s\n", WiFi.localIP().toString().c_str());
}

// O backend exige recorded_at com timezone; sincronizamos via NTP para obter UTC real.
void syncTime() {
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    Serial.print("Sincronizando horario via NTP");
    time_t now = time(nullptr);
    while (now < 24 * 3600) {
        delay(500);
        Serial.print(".");
        now = time(nullptr);
    }
    Serial.println("\nHorario sincronizado.");
}

String isoTimestampNow() {
    time_t now = time(nullptr);
    struct tm utc;
    gmtime_r(&now, &utc);
    char buffer[25];
    strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &utc);
    return String(buffer);
}

// event_id so precisa ser unico por dispositivo; combina epoch + millis do boot.
String nextEventId() {
    return String(DEVICE_SERIAL) + "-" + String((unsigned long)time(nullptr)) + "-" +
           String(millis());
}

} // namespace

void setup() {
    Serial.begin(115200);
    connectWiFi();
    syncTime();
    flowSensor.begin(FLOW_SENSOR_PIN, FLOW_PULSES_PER_LITER);
    telemetryClient.begin(AQUAFLOW_API_BASE_URL, DEVICE_SERIAL, DEVICE_KEY);
    lastSampleAt = millis();
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        connectWiFi();
    }

    telemetryClient.flushPending();

    unsigned long now = millis();
    if (now - lastSampleAt >= SAMPLE_INTERVAL_MS) {
        unsigned long elapsed = now - lastSampleAt;
        lastSampleAt = now;

        TelemetryReading reading;
        reading.eventId = nextEventId();
        reading.recordedAtIso = isoTimestampNow();
        reading.cumulativeVolumeLiters = flowSensor.cumulativeLiters();
        reading.flowRateLitersMinute = flowSensor.instantaneousFlowLitersPerMinute(elapsed);
        reading.signalDbm = WiFi.RSSI();
        flowSensor.resetInterval();

        SendResult result = telemetryClient.send(reading);
        if (result == SendResult::NetworkError) {
            Serial.println("Falha de rede ao enviar leitura; adicionando a fila local.");
            telemetryClient.enqueuePending(reading);
        } else if (result == SendResult::Rejected) {
            Serial.println("API rejeitou a leitura (contrato ou credencial invalida).");
        } else {
            // Pulsos crus no log para calibracao: passe um volume conhecido e
            // divida estes pulsos acumulados pelos litros reais (ver README).
            Serial.printf("Leitura enviada: %s L acumulados, %s L/min, %lu pulsos acumulados\n",
                           String(reading.cumulativeVolumeLiters, 3).c_str(),
                           String(reading.flowRateLitersMinute, 3).c_str(),
                           flowSensor.cumulativePulses());
        }
    }
}
