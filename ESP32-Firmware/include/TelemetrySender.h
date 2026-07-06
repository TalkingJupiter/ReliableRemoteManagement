#pragma once

#include <Arduino.h>
#include "RuntimeConfig.h"

// Lightweight MQTT sender for telemetry JSON payloads over a W5500.

class TelemetrySender {
  public:
    bool begin();
    void loop();
    bool isUp() const;
    void setConfig(const RuntimeConfig& cfg);
    
    bool hello();
    bool sendMQTT(const char* jsonPayload);

    // Formats ESP32 base MAC (EFUSE) as "AA:BB:CC:DD:EE:FF".
    static String deviceMacString();
  private:
    RuntimeConfig config_;
};


