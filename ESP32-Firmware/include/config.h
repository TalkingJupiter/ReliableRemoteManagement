#pragma once
#include <Arduino.h>

// ==================
// BUILD-TIME CONFIG
// ==================
// PlatformIO passes most settings via -D flags in platformio.ini.
// These defaults are only used when a flag is NOT provided.

#ifndef DEVICE_ID
  #error "DEVICE_ID must be set in platformio.ini (e.g., -DDEVICE_ID=65 for 'A')"
#endif

// ------------------
// Heartbeat (UART)
// ------------------
#ifndef HB_UART_NUM
  #define HB_UART_NUM 1
#endif

// Keep compatibility with older names.
#if !defined(HB_UART_RX_PIN) && defined(HB_RX_PIN)
  #define HB_UART_RX_PIN HB_RX_PIN
#endif
#if !defined(HB_UART_TX_PIN) && defined(HB_TX_PIN)
  #define HB_UART_TX_PIN HB_TX_PIN
#endif
#if !defined(HB_UART_BAUD) && defined(HB_BAUD)
  #define HB_UART_BAUD HB_BAUD
#endif

#ifndef HB_UART_RX_PIN
  #define HB_UART_RX_PIN 16
#endif
#ifndef HB_UART_TX_PIN
  #define HB_UART_TX_PIN 17
#endif
#ifndef HB_UART_BAUD
  #define HB_UART_BAUD 115200
#endif

// User requirement: send every 500ms, fail on 2000ms
#ifndef HB_SEND_MS
  #define HB_SEND_MS 500
#endif
#ifndef HB_TIMEOUT_MS
  #define HB_TIMEOUT_MS 2000
#endif

// Used by the older RoleManager logic (still fine to keep defined).
#ifndef HB_TAKEOVER_HOLD_MS
  #define HB_TAKEOVER_HOLD_MS 5000
#endif

// ------------------
// 1-Wire busses
// ------------------
#ifndef ONE_WIRE_BUS_COOL
  #define ONE_WIRE_BUS_COOL 4
#endif
#ifndef ONE_WIRE_BUS_EXHAUST
  #define ONE_WIRE_BUS_EXHAUST 21
#endif

// ------------------
// W5500 Ethernet
// ------------------
// These are *defaults*. Adjust pins for your wiring.
#ifndef W5500_CS_PIN
  #define W5500_CS_PIN 5
#endif

// VSPI default pins on ESP32 devkits: SCK=18, MISO=19, MOSI=23
#ifndef W5500_SCK_PIN
  #define W5500_SCK_PIN 18
#endif
#ifndef W5500_MISO_PIN
  #define W5500_MISO_PIN 19
#endif
#ifndef W5500_MOSI_PIN
  #define W5500_MOSI_PIN 23
#endif

// Optional. Set to an ESP32 GPIO if the W5500 RST pin is wired to firmware control.
// Leave as -1 if RST is tied high externally or the module handles reset itself.
#ifndef W5500_RST_PIN
  #define W5500_RST_PIN 2
#endif

// Telemetry destination (Radxa)
#ifndef RADXA_UDP_PORT
  #define RADXA_UDP_PORT 5005
#endif

// If you don't define RADXA_IP_* we will default to 192.168.1.10
#ifndef RADXA_IP_A
  #define RADXA_IP_A 192
#endif
#ifndef RADXA_IP_B
  #define RADXA_IP_B 168
#endif
#ifndef RADXA_IP_C
  #define RADXA_IP_C 50
#endif
#ifndef RADXA_IP_D
  #define RADXA_IP_D 115
#endif

// How often to send the JSON payload.
#ifndef TELEMETRY_SEND_MS
  #define TELEMETRY_SEND_MS 5000
#endif

// ------------------
// Relay/switch pins
// ------------------
// NOTE: This version of the project does NOT use relays/switching logic.
// We keep these defines so existing files still compile, but main.cpp does not touch them.
#ifndef RELAY_A_PIN
  #define RELAY_A_PIN 25
#endif
#ifndef RELAY_B_PIN
  #define RELAY_B_PIN 26
#endif
#ifndef RELAY_ACTIVE_LOW
  #define RELAY_ACTIVE_LOW 1
#endif
#ifndef BREAK_BEFORE_MAKE_MS
  #define BREAK_BEFORE_MAKE_MS 30
#endif
