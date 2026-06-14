#include <Arduino.h>
#include "config.h"
#include "Heartbeat.h"
#include "TemperatureBus.h"
#include "TelemetrySender.h"

HardwareSerial HBSerial(HB_UART_NUM);
Heartbeat hb(HBSerial);
TemperatureBus tempBus;
TelemetrySender net;

static inline bool isControllerA() { return DEVICE_ID == 'A' || DEVICE_ID == 65; }
static inline bool isControllerB() { return DEVICE_ID == 'B' || DEVICE_ID == 66; }

void heartbeatTask(void *param){
  uint32_t lastSend = 0;
  
  while(true){
    const uint32_t now = millis();

    //Always read the incoming data
    hb.tick();

    //Send own heartbeat periodically
    if((uint32_t)(now - lastSend) >= HB_SEND_MS){
      lastSend = now;
      hb.send((char)DEVICE_ID, now);
    }

    vTaskDelay(pdMS_TO_TICKS(5));
  }
}

static void printTemps() {
  Serial.printf(
    "[TEMP] inlet: %.2f %.2f %.2f | exhaust: %.2f %.2f %.2f\n",
    tempBus.intakeC(0), tempBus.intakeC(1), tempBus.intakeC(2),
    tempBus.exhaustC(0), tempBus.exhaustC(1), tempBus.exhaustC(2)
  );
}

static void maybePrintTemps() {
  if (tempBus.hasNewSample()) {
    tempBus.clearNewSampleFlag();
    printTemps();
  }
}

static void appendTempArray(char* out, size_t outSz, const float vals[TemperatureBus::SENSORS_PER_BUS]) {
  // Writes something like: [21.23, 22.00, null]
  // NAN -> null
  size_t used = strnlen(out, outSz);
  if (used >= outSz) return;

  auto append = [&](const char* s) {
    size_t u = strnlen(out, outSz);
    if (u < outSz) strncat(out, s, outSz - u - 1);
  };

  append("[");
  for (uint8_t i = 0; i < TemperatureBus::SENSORS_PER_BUS; i++) {
    if (i) append(", ");
    if (isnan(vals[i])) {
      append("null");
    } else if (vals[i] == 85.0f) {
      append("null");
    } else {
      char b[16];
      snprintf(b, sizeof(b), "%.2f", (double)vals[i]);
      append(b);
    }
  }
  append("]");
}

static void buildTelemetryJson(char* out, size_t outSz,
                               const char* macStr,
                               uint32_t nowMs,
                               bool aAlive,
                               bool bAlive,
                               const float cool[TemperatureBus::SENSORS_PER_BUS],
                               const float exhaust[TemperatureBus::SENSORS_PER_BUS],
                               bool failoverOccurred,
                               const char* failoverDetails) {
  // NOTE: Kept close to the JSON structure shown in the image.
  // We avoid ArduinoJson to keep dependencies minimal.
  if (!out || outSz == 0) return;
  out[0] = '\0';

  // Pre-build temperature arrays
  char coolArr[96] = {0};
  char exhArr[96] = {0};
  appendTempArray(coolArr, sizeof(coolArr), cool);
  appendTempArray(exhArr, sizeof(exhArr), exhaust);

  // Escape details minimally (replace \" with ').
  char detailsSafe[128];
  size_t di = 0;
  if (!failoverDetails) failoverDetails = "";
  for (size_t i = 0; failoverDetails[i] && di + 1 < sizeof(detailsSafe); i++) {
    char c = failoverDetails[i];
    if (c == '"') c = '\'';
    if ((uint8_t)c < 0x20) c = ' '; // strip control chars
    detailsSafe[di++] = c;
  }
  detailsSafe[di] = '\0';

  snprintf(
    out, outSz,
    "{\n"
    "  \"message_type\": \"telemetry\",\n\n"
    "  \"device\": {\n"
    "    \"mac\": \"%s\"\n"
    "  },\n\n"
    "  \"timestamp_device_ms\": %lu,\n\n"
    "  \"items\": [\n"
    "    {\n"
    "      \"kind\": \"heartbeat\",\n"
    "      \"controller_a_alive\": %s,\n"
    "      \"controller_b_alive\": %s\n"
    "    },\n"
    "    {\n"
    "      \"kind\": \"sensors\",\n"
    "      \"buses\": [\n"
    "        {\n"
    "          \"bus\": \"inlet\",\n"
    "          \"temperatures_c\": %s\n"
    "        },\n"
    "        {\n"
    "          \"bus\": \"exhaust\",\n"
    "          \"temperatures_c\": %s\n"
    "        }\n"
    "      ]\n"
    "    },\n"
    "    {\n"
    "      \"kind\": \"event\",\n"
    "      \"type\": \"failover\",\n"
    "      \"occurred\": %s,\n"
    "      \"details\": \"%s\"\n"
    "    }\n"
    "  ]\n"
    "}\n",
    macStr,
    (unsigned long)nowMs,
    aAlive ? "true" : "false",
    bAlive ? "true" : "false",
    coolArr,
    exhArr,
    failoverOccurred ? "true" : "false",
    detailsSafe
  );
}

void setup() {
  Serial.begin(115200);
  delay(200);

  Serial.println();
  Serial.printf("Booting Controller %c\n", (char)DEVICE_ID);

  // Start heartbeat UART link and create the Heartbeat task
  hb.begin(HB_UART_RX_PIN, HB_UART_TX_PIN, HB_UART_BAUD);
  xTaskCreatePinnedToCore(heartbeatTask, "Heartbeat", 4096, nullptr, 3, nullptr, 1);

  // Start temperature buses (intake + exhaust)
  tempBus.begin(ONE_WIRE_BUS_COOL, ONE_WIRE_BUS_EXHAUST);

  // Start Ethernet telemetry
  bool netOK = net.begin();
  if(!netOK){
    Serial.println("[SETUP NET] Ethernet init failed or link is down");
  }

  Serial.println("Heartbeat + TemperatureBus started\n");

  // Optional sanity check (keep if you want)
  Serial.printf("[TEMP:init] intakeN=%u exhaustN=%u\n",
                tempBus.intakeDeviceCount(),
                tempBus.exhaustDeviceCount());
}

void loop() {
  const uint32_t now = millis();

  /*
  // 1) Always parse RX
  // hb.tick();

  // 2) Send heartbeat periodically
  // static uint32_t lastSend = 0;
  // if ((uint32_t)(now - lastSend) >= (uint32_t)HB_SEND_MS) {
  //   lastSend = now;
  //   hb.send((char)DEVICE_ID, now);
  // }
*/


  // 3) Temperature sampling (tick exactly once per loop)
  tempBus.tick(now);

  // 4) Heartbeat status
  const bool peerAlive = hb.peerAlive(now, HB_TIMEOUT_MS);
  const uint32_t ageMs = (hb.lastRxMS() == 0) ? 0 : (now - hb.lastRxMS());

  // Determine A/B alive flags (self is always alive)
  const char myId = (char)DEVICE_ID;
  const bool controllerAAlive = (myId == 'A') ? true : peerAlive;
  const bool controllerBAlive = (myId == 'B') ? true : peerAlive;

  // Failover event tracking (purely logical in this "no-relay" version)
  static bool failoverOccurred = false;
  static char failoverDetails[96] = {0};
  if ((myId == 'B') && !failoverOccurred) {
    const bool healthy = (hb.peerId() == 'A') && peerAlive;
    if (!healthy && hb.peerId() == 'A') {
      failoverOccurred = true;
      snprintf(failoverDetails, sizeof(failoverDetails),
               "B took over after %lu ms heartbeat silence", (unsigned long)ageMs);
    }
  }

  // 5) Telemetry send (only active controller sends)
  static uint32_t lastTelemetry = 0;

  // Determine whether B should take over sending:
  // - "healthy" means A is the peer and is alive
  static bool everSawA = false;
  if (hb.peerId() == 'A') everSawA = true;

  const bool healthyA = (hb.peerId() == 'A') && peerAlive;

  // Optional boot grace: if A never appears, let B start sending after a few seconds
  const uint32_t BOOT_GRACE_MS = 5000;
  const bool allowBootTakeover = (now > BOOT_GRACE_MS) && !everSawA;

  bool iAmActiveSender = false;
  if (isControllerA()) {
    iAmActiveSender = true;                  // A always sends
  } else if (isControllerB()) {
    // B sends only if A is unhealthy (after timeout) OR A never appeared after grace
    iAmActiveSender = (!healthyA && everSawA) || allowBootTakeover;
  }

  if (iAmActiveSender && (uint32_t)(now - lastTelemetry) >= (uint32_t)TELEMETRY_SEND_MS) {
    lastTelemetry = now;

    float cool[TemperatureBus::SENSORS_PER_BUS];
    float exhaust[TemperatureBus::SENSORS_PER_BUS];
    for (uint8_t i = 0; i < TemperatureBus::SENSORS_PER_BUS; i++) {
      cool[i] = tempBus.intakeC(i);
      exhaust[i] = tempBus.exhaustC(i);
    }

    static char json[768];
    const String macStr = TelemetrySender::deviceMacString();
    buildTelemetryJson(json, sizeof(json),
                       macStr.c_str(), now,
                       controllerAAlive, controllerBAlive,
                       cool, exhaust,
                       failoverOccurred,
                       failoverDetails);

    const bool ok = net.sendUDP(json);
    if (!ok) {
      Serial.println("[NETWORK] Telemetry send failed (link down or UDP error)");
    } else {
      Serial.println("[NETWORK] Telemetry Sent Successfully");
    }
  }

  // Controller A: prints HB status periodically + always prints temps when sampled
  if (isControllerA()) {
    static uint32_t lastStatus = 0;
    if ((uint32_t)(now - lastStatus) >= 1000) {
      lastStatus = now;
      Serial.printf("[HB:A] peer=%c, alive=%d, age_ms=%lu\n",
                    hb.peerId(),
                    peerAlive ? 1 : 0,
                    (unsigned long)ageMs);
    }

    maybePrintTemps();
  }

  // Controller B: prints temps only when A is unhealthy; logs transitions
  if (isControllerB()) {
    static bool lastHealthy = false;
    static bool everHealthy = false;

    // Your original policy: B considers "healthy" only if the peer is A and alive.
    const bool healthy = (hb.peerId() == 'A') && peerAlive;

    if (lastHealthy && !healthy) {
      Serial.printf("[ALERT:B] Lost heartbeat from A (timeout=%d ms). peer=%c age_ms=%lu\n",
                    (int)HB_TIMEOUT_MS, hb.peerId(), (unsigned long)ageMs);
      Serial.printf("[INFO:B] Trying to recover the bus communication...\n");
    }

    if (!lastHealthy && healthy) {
      if (everHealthy) {
        Serial.printf("[RECOVER:B] Heartbeat from A restored. age_ms=%lu\n",
                      (unsigned long)ageMs);
        Serial.printf("[INFO:B] Releasing the bus communication to device %c\n", hb.peerId());
      }
      everHealthy = true;
    }

    lastHealthy = healthy;

    // Print temps continuously while unhealthy (more useful than edge-only)
    if (!healthy) {
      maybePrintTemps();
    } else {
      // Stay quiet when healthy.
    }
  }

  vTaskDelay(pdMS_TO_TICKS(10));
}
