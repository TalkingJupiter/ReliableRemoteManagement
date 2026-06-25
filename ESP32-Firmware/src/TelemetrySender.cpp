#include "TelemetrySender.h"
#include "config.h"

#include <SPI.h>
#include <Ethernet.h>
#include <EthernetUdp.h>

#ifdef ESP32
  #include <esp_mac.h>
#endif

static EthernetUDP gUdp;
static bool gEthUp = false;

static IPAddress radxaIP() {
  return IPAddress(RADXA_IP_A, RADXA_IP_B, RADXA_IP_C, RADXA_IP_D);
}

static void printMac(const byte mac[6]) {
  Serial.printf("%02X:%02X:%02X:%02X:%02X:%02X",
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

static const char* hardwareStatusName(EthernetHardwareStatus status) {
  switch (status) {
    case EthernetNoHardware: return "no hardware";
    case EthernetW5100: return "W5100";
    case EthernetW5200: return "W5200";
    case EthernetW5500: return "W5500";
    default: return "unknown";
  }
}

static const char* linkStatusName(EthernetLinkStatus status) {
  switch (status) {
    case Unknown: return "unknown";
    case LinkON: return "on";
    case LinkOFF: return "off";
    default: return "unknown";
  }
}

static void resetW5500IfConfigured() {
  if (W5500_RST_PIN < 0) {
    Serial.println("[NET] W5500 reset pin not configured");
    return;
  }

  Serial.printf("[NET] Resetting W5500 on GPIO %d\n", W5500_RST_PIN);
  pinMode(W5500_RST_PIN, OUTPUT);
  digitalWrite(W5500_RST_PIN, LOW);
  delay(50);
  digitalWrite(W5500_RST_PIN, HIGH);
  delay(250);
}

String TelemetrySender::deviceMacString() {
  uint8_t mac[6] = {0};

  #ifdef ESP32
    // ESP32 "base MAC" is stable and unique per chip.
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
  #else
    // Fallback (won't be unique).
    mac[0] = 0xAA; mac[1] = 0xBB; mac[2] = 0xCC;
    mac[3] = 0xDD; mac[4] = 0xEE; mac[5] = 0xFF;
  #endif

  char buf[18];
  snprintf(buf, sizeof(buf), "%02X:%02X:%02X:%02X:%02X:%02X",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  return String(buf);
}

bool TelemetrySender::begin() {
  resetW5500IfConfigured();

  // Initialize SPI for W5500
  SPI.begin(W5500_SCK_PIN, W5500_MISO_PIN, W5500_MOSI_PIN, W5500_CS_PIN);
  Ethernet.init(W5500_CS_PIN);

  // W5500 requires a MAC for Ethernet.begin (even if we use DHCP).
  // We'll derive one from the ESP32 base MAC.
  uint8_t base[6] = {0};
  #ifdef ESP32
    esp_read_mac(base, ESP_MAC_WIFI_STA);
  #else
    base[0]=0xDE; base[1]=0xAD; base[2]=0xBE; base[3]=0xEF; base[4]=0x00; base[5]=0x01;
  #endif
  byte ethMac[6] = { base[0], base[1], base[2], base[3], base[4], base[5] };

  Serial.println("[NET] Initializing W5500...");
  Serial.print("[NET] MAC=");
  printMac(ethMac);
  Serial.println();
  Serial.print("[NET] Hardware=");
  const EthernetHardwareStatus hardwareStatus = Ethernet.hardwareStatus();
  Serial.println(hardwareStatusName(hardwareStatus));
  if (hardwareStatus == EthernetNoHardware) {
    gEthUp = false;
    Serial.println("[NET] W5500 not detected on SPI. Check 3V3, GND, SCK, MISO, MOSI, CS, and RST.");
    return false;
  }

  Serial.print("[NET] Link before DHCP=");
  Serial.println(linkStatusName(Ethernet.linkStatus()));

  if (Ethernet.begin(ethMac) == 0) {
    gEthUp = false;
    Serial.println("[NET] DHCP failed. Telemetry will not send.");
    return false;
  }

  delay(200);

  if (Ethernet.linkStatus() == LinkON) {
    gEthUp = true;
    Serial.println("[NET] Link up. DHCP lease acquired.");
    Serial.print("[NET] Local IP=");
    Serial.println(Ethernet.localIP());
    Serial.print("[NET] Subnet=");
    Serial.println(Ethernet.subnetMask());
    Serial.print("[NET] Gateway=");
    Serial.println(Ethernet.gatewayIP());
    Serial.print("[NET] DNS=");
    Serial.println(Ethernet.dnsServerIP());
    Serial.print("[NET] Destination=");
    Serial.print(radxaIP());
    Serial.print(":");
    Serial.println((uint16_t)RADXA_UDP_PORT);
  } else {
    gEthUp = false;
    Serial.println("[NET] Link DOWN (check cable/switch). Telemetry will not send.");
    return false;
  }

  // UDP does not need bind, but begin() sets a local port.
  gUdp.begin(0);
  return gEthUp;
}

bool TelemetrySender::isUp() const {
  // Update link status opportunistically.
  gEthUp = (Ethernet.linkStatus() == LinkON);
  return gEthUp;
}

bool TelemetrySender::sendUDP(const char* jsonPayload) {
  if (!jsonPayload || !jsonPayload[0]) return false;
  if (!isUp()) return false;

  const IPAddress dst = radxaIP();

  if (gUdp.beginPacket(dst, (uint16_t)RADXA_UDP_PORT) != 1) {
    return false;
  }
  gUdp.write((const uint8_t*)jsonPayload, strlen(jsonPayload));
  return (gUdp.endPacket() == 1);
}
