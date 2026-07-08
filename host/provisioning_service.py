import socket
import json
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

# Temporary development registry -> Move it to DB when its ready
DEVICE_REGISTRY = {
    "ECE3347C07D0": {
        "rack_id": "rack01",
        "role": "Primary",
    },
    "ECE3347C07D1": {
        "rack_id": "rack01",
        "role": "Standby",
    }
}

def get_local_ip():
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    return local_ip

def build_config(mac: str, device: dict) -> dict:
# FUTURE: When a general system is working with DB and a dashboard implement a modifiable telemetry collect timing

    rack_id = device["rack_id"]
    role = device["role"]

    return{
        "message_type": "config",
        "mac": mac,
        "configured": True,
        "enabled": True, # Implement a new logic to receive if it is enabled or not
        "rack_id": rack_id,
        "role": role
    }

def on_connect(client: mqtt.Client, userdata, flags, reason_code, properties):
    print(f"[MQTT] Connected with reason: {reason_code}") # Convert to a log to register to docker log file

    client.subscribe("repacss/device/+/hello", qos=1)

def on_message(client: mqtt.Client, userdata, msg):
    topic = msg.topic
    payload_txt = msg.payload.decode("utf-8")

    print(f"[RX] {topic} {payload_txt}")
    
    parts = topic.split("/")
    mac = parts[2]

    device = DEVICE_REGISTRY.get(mac)
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


BROKER_HOST = get_local_ip()
BROKER_PORT = 1883 #TODO: Change this to get it from docker compose file from mosquitto container

client = mqtt.Client(
    CallbackAPIVersion.VERSION2, 
    client_id="repacss-provisioning-service"
)

client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER_HOST, BROKER_PORT)
