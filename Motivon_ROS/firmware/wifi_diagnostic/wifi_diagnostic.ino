#include <Arduino.h>
#include <WiFi.h>

#include "wifi_config.h"

constexpr uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000;
constexpr uint32_t RETRY_DELAY_MS = 2000;
constexpr uint32_t STATUS_PERIOD_MS = 1000;

bool connectWifi() {
  WiFi.disconnect(true);
  delay(100);
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  WiFi.begin(MOTIVON_WIFI_SSID, MOTIVON_WIFI_PASSWORD);

  const uint32_t started_ms = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - started_ms >= WIFI_CONNECT_TIMEOUT_MS) {
      return false;
    }
    delay(50);
  }
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("[wifi_test] Wi-Fi-only diagnostic starting");
  Serial.printf("[wifi_test] MAC=%s\n", WiFi.macAddress().c_str());

  while (!connectWifi()) {
    Serial.println("[wifi_test] Connection failed; retrying");
    delay(RETRY_DELAY_MS);
  }

  Serial.printf(
      "[wifi_test] Connected; IP=%s gateway=%s RSSI=%d dBm\n",
      WiFi.localIP().toString().c_str(),
      WiFi.gatewayIP().toString().c_str(),
      WiFi.RSSI());
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[wifi_test] Disconnected; reconnecting");
    while (!connectWifi()) {
      delay(RETRY_DELAY_MS);
    }
  }

  Serial.printf(
      "[wifi_test] IP=%s RSSI=%d dBm\n",
      WiFi.localIP().toString().c_str(),
      WiFi.RSSI());
  delay(STATUS_PERIOD_MS);
}
