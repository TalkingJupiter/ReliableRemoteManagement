import datetime
import json
import paho.mqtt.client as mqtt
from app.db import connect as db_connect

conn = db_connect()

def on_connect(client: mqtt.Client, userdata, flags, rc, properties):
    print(f"[MQTT] Connected with result code {rc}")

    # Firmware publishes on repacss/devices/<mac>/<type>, so subscriptions and
    # the parts[] parsing below both key off that shape.
    client.subscribe("repacss/devices/+/telemetry", qos=0)
    client.subscribe("repacss/devices/+/status", qos=0)
    client.subscribe("repacss/devices/+/event", qos=1)
    client.subscribe("repacss/devices/+/ack", qos=1)  # device-level acknowledgement

def on_message(client: mqtt.Client, userdata, msg):
    topic = msg.topic
    payload_txt = msg.payload.decode("utf-8")

    print(f"[RX] {topic} {payload_txt}")

    parts = topic.split("/")
    mac = parts[2]
    message_type = parts[3]

    try:
        payload = json.loads(payload_txt)
    except json.JSONDecodeError:
        print(f"[WARN] Invalid JSON payload from {mac}: {payload_txt}")
        return

    # TODO: Check if the mac address is registered in the database, if not record under unknown devices table
    if not is_registered(mac):
        print(f"[WARN] Unregistered device {mac} sent a message. Ignoring.")
        print(f"[WARN] UNKNOWN DEVICE PAYLOAD: {payload_txt}")
        return

    if message_type == "telemetry":
        rack_id = rack_filter(mac) # FUTURE: This should be cached in memory to avoid repeated DB lookups for the same device
        ts = datetime.datetime.now(datetime.timezone.utc)

        sensors = next(item for item in payload.get("items", []) if item.get("kind") == "sensors")
        if sensors:
            for bus in sensors.get("buses", []):
                bus_name = bus["bus"]
                for sensor_index , temp in enumerate(bus.get("temperatures_c", [])):
                    handle_telemetry(conn, ts, mac, rack_id, bus_name, sensor_index, temp)
        
    elif message_type == "status":
        handle_status(mac, payload)
    elif message_type == "event":
        handle_event(mac, payload)
    elif message_type == "ack":
        handle_ack(mac, payload)
    else:
        print(f"[WARN] Unknown message type '{message_type}' from {mac}")

def is_registered(mac):
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM repacss_environment.device_map WHERE mac = %s",
                (mac,)
            )
            return cur.fetchone() is not None

def rack_filter(mac):
    print(f"[INFO] Filtering rack_id for device {mac}")
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rack_id FROM repacss_environment.device_map WHERE mac = %s",
                (mac,)
            )
            result = cur.fetchone()
            if result:
                return result[0]
            else:
                print(f"[WARN] No rack_id found for device {mac}")
                return None

def handle_telemetry(conn, ts, mac, rack_id, bus, sensor_index, temp_c):
    print(f"[INFO] Telemetry received from {mac}")

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO repacss_environment.telemetry (ts_host, mac, rack_id, bus, sensor_index, temp_c)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (ts, mac, rack_id, bus, sensor_index, temp_c)
            )

def handle_status(mac, payload):
    print(f"[INFO] Status from {mac}: {payload}")
    #TODO: Implement status handling logic, e.g., update device state in the database or log the status information
    #WARNING: Status handling is handled in the telemetry message type for 0.0.1 version of the firmware. Needs Updating
    raise NotImplementedError("Status handling is not implemented yet.")
    

def handle_event(mac, payload):
    print(f"[INFO] Event from {mac}: {payload}")
    #WARNING: There is no event handling in the current firmware version 0.0.1. This is a placeholder for future event handling logic.
    raise NotImplementedError("Event handling is not implemented yet.")

def handle_ack(mac, payload):
    print(f"[INFO] Acknowledgement from {mac}: {payload}")
    raise NotImplementedError("Acknowledgement handling is not implemented yet.")