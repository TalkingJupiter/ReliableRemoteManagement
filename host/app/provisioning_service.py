import json
import time
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from app.config import settings
from app.db import connect as db_connect

conn = db_connect()

_device_map = {}
_device_map_ts = 0.0
_DEVICE_MAP_TTL = 60.0  # seconds


def cache_device_map() -> dict:
    global _device_map, _device_map_ts
    now = time.monotonic()
    if now - _device_map_ts > _DEVICE_MAP_TTL:
        _device_map = get_device_map()
        _device_map_ts = now
    return _device_map

def get_device_map() -> dict:
    """Fetch the device registry from the database and return a mapping of mac addresses to device info."""
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                # macaddr renders as 'ec:e3:34:7c:07:d0', but devices identify
                # themselves with the compact uppercase form in topics and in
                # the hello payload. Normalize here so the dict keys match the
                # mac we parse off the topic.
                cur.execute(
                    "SELECT upper(replace(mac::text, ':', '')), rack_id, role, enabled "
                    "FROM repacss_environment.device_map WHERE retired = false"
                )
                rows = cur.fetchall()
                return {row[0]: {"rack_id": row[1], "role": row[2], "enabled": row[3]} for row in rows}
    except Exception as error:
        print(f"[ERROR] Failed to fetch device registry from database: {error}")
        return {}

def get_device_state() -> dict:
    """Fetch the device state from the database and return a mapping of mac addresses to their current state."""
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                # Same normalization as get_device_map: keys must match the
                # compact uppercase mac the devices report.
                cur.execute(
                    "SELECT upper(replace(mac::text, ':', '')), running_firmware_version "
                    "FROM repacss_environment.current_status "
                    "WHERE last_seen > now() - interval '1 minutes'"
                )
                rows = cur.fetchall()
                return {row[0]: {"firmware_version": row[1]} for row in rows}
    except Exception as error:
        print(f"[ERROR] Failed to fetch device state from database: {error}")
        return {}

def upsert_device_state(mac: str, fw: str) -> None:
    """Persist the device's reported firmware version and liveness into current_status."""
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO repacss_environment.current_status
                        (mac, alive, last_seen, running_firmware_version)
                    VALUES (%s, true, now(), %s)
                    ON CONFLICT (mac) DO UPDATE
                    SET alive = EXCLUDED.alive,
                        last_seen = EXCLUDED.last_seen,
                        running_firmware_version = EXCLUDED.running_firmware_version
                    """,
                    (mac, fw),
                )
    except Exception as error:
        print(f"[ERROR] Failed to upsert device state for {mac}: {error}")


def is_enabled(mac: str, role: str) -> bool:
    # Both Primary and Standby are enabled -- role + heartbeat decides who
    # actually transmits. enabled:false is the remote kill-switch (OTA /
    # maintenance), not the standby-quiet mechanism.
    return role in ("Primary", "Standby")


def build_config(mac: str, device: dict) -> dict:
# FUTURE: When a general system is working with DB and a dashboard implement a modifiable telemetry collect timing

    rack_id = device["rack_id"]
    role = device["role"]

    return{
        "message_type": "config",
        "mac": mac,
        "configured": True,
        "enabled": is_enabled(mac, role),
        # Sent as a string: the firmware parses rack_id with as<const char*>(),
        # which yields null for a JSON integer and fails config validation.
        "rack_id": str(rack_id),
        "role": role
    }

def on_connect(client: mqtt.Client, userdata, flags, reason_code, properties):
    print(f"[MQTT] Connected with reason: {reason_code}") # Convert to a log to register to docker log file

    client.subscribe("repacss/devices/+/hello", qos=1)

def on_message(client: mqtt.Client, userdata, msg):
    topic = msg.topic
    payload_txt = msg.payload.decode("utf-8")

    print(f"[RX] {topic} {payload_txt}")
    
    parts = topic.split("/")
    mac = parts[2]

    try:
        hello = json.loads(payload_txt)
    except json.JSONDecodeError:
        print(f"[WARN] Invalid JSON payload from {mac}: {payload_txt}")
        return

    fw = hello.get("firmware_version", "unknown")
    print(f"[INFO] Device {mac} running firmware version: {fw}")
    upsert_device_state(mac, fw)

    device = cache_device_map().get(mac)
    config_topic = f"repacss/devices/{mac}/config"

    if device is None:
        print(f"[WARN] Unknown device: {mac}")

        unknown_status={
            "message_type": "config",
            "mac": mac,
            "configured": False,
            "reason": "unknown mac"
        }

        
        client.publish(config_topic, json.dumps(unknown_status), qos=1, retain=False)

        return

    config = build_config(mac, device)
    print(f"[TX] Sending config to {config_topic}")

    client.publish(config_topic, json.dumps(config), qos=1, retain=False)


client = mqtt.Client(
    CallbackAPIVersion.VERSION2,
    client_id="repacss-provisioning-service"
)

client.on_connect = on_connect
client.on_message = on_message

client.connect(settings.broker_host, settings.broker_port)
client.loop_forever()
