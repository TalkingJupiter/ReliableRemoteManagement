import datetime
import json
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from app.config import settings
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
        event_type = payload.get("event_type")
        if not event_type:
            print(f"[WARN] Event from {mac} has no event_type, skipping: {payload_txt}")
        else:
            details = payload.get("details")
            rack_id = rack_filter(mac)
            role = role_filter(mac)
            ts = datetime.datetime.now(datetime.timezone.utc)
            handle_event(conn, ts, mac, event_type, details, rack_id, role)
    elif message_type == "ack":
        handle_ack(mac, payload)
    else:
        print(f"[WARN] Unknown message type '{message_type}' from {mac}")

def is_registered(mac):
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM repacss_environment.device_map WHERE mac = %s",
                (mac,)
            )
            return cur.fetchone() is not None

def rack_filter(mac):
    print(f"[INFO] Filtering rack_id for device {mac}")
    with conn.transaction():
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

def role_filter(mac):
    print(f"[INFO] Filtering role for device {mac}")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role FROM repacss_environment.device_map WHERE mac = %s",(mac,)
            )
            result = cur.fetchone()
            if result:
                return result[0]
            else:
                print(f"[WARN] No role found for device {mac}")
                return None

def handle_telemetry(conn, ts, mac, rack_id, bus, sensor_index, temp_c):
    print(f"[INFO] Telemetry received from {mac}")
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO repacss_environment.telemetry (ts_host, mac, rack_id, bus, sensor_index, temperature_celsius)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (ts, mac, rack_id, bus, sensor_index, temp_c)
                )
    except Exception as error:
        print(f"[ERROR] Failed to insert telemetry for {mac}: {error}")

def handle_status(mac, payload):
    print(f"[INFO] Status from {mac}: {payload}")
    #TODO: Implement status handling logic, e.g., update device state in the database or log the status information
    #WARNING: Status handling is handled in the telemetry message type for 0.0.1 version of the firmware. Needs Updating
    raise NotImplementedError("Status handling is not implemented yet.")
    

def handle_event(conn, ts, mac, event_type, details, rack_id, role):
    print(f"[INFO] Event received from {mac}")
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO repacss_environment.events (ts_host, mac, event_type, details, rack_id, role)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """, (ts, mac, event_type, details, rack_id, role)
                )
    except Exception as error:
        print(f"[ERROR] Failed to insert event for {mac}: {error}")

def handle_ack(mac, payload):
    print(f"[INFO] Acknowledgement from {mac}: {payload}")
    raise NotImplementedError("Acknowledgement handling is not implemented yet.")

client = mqtt.Client(
    CallbackAPIVersion.VERSION2,
    client_id="repacss-ingestion-service",
)

client.on_connect = on_connect
client.on_message = on_message

client.connect(settings.broker_host, settings.broker_port)
client.loop_forever()  # Blocking call to process network traffic and dispatch callbacks
