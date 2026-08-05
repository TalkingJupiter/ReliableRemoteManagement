"""Tests for app.provisioning_service.

Functions covered and their cases:

is_enabled(mac, role)
- Primary -> True, Standby -> True, any other role -> False.

build_config(mac, device)
- Returns the full config dict with configured=True and enabled from is_enabled.
- Missing a required device key raises KeyError (surfaces bad registry data).

get_device_state()
- Maps DB rows to {mac: {firmware_version}}.
- Returns {} on a DB error.

upsert_device_state(mac, fw)
- Runs the current_status upsert with (mac, fw) parameters.
- Swallows DB errors (logs, does not raise) so a hello is never lost to a write blip.

(The device_map cache moved to app.device_registry; see test_device_registry.py.)

on_connect(...)
- Subscribes to the hello topic.

on_message(...)
- Known device -> upserts state and publishes a config.
- Unknown device -> publishes configured:false with reason "unknown mac".
- Invalid JSON -> does nothing (no upsert, no publish).
"""

import json
from unittest.mock import MagicMock

import pytest

import app.provisioning_service as prov


# --- is_enabled ---------------------------------------------------------------

@pytest.mark.parametrize("role,expected", [
    ("Primary", True),
    ("Standby", True),
    ("Unknown", False),
    ("controllerA", False),
    ("", False),
])
def test_is_enabled(role, expected):
    assert prov.is_enabled("AABBCCDDEEFF", role) is expected


# --- build_config -------------------------------------------------------------

def test_build_config_primary_full_shape():
    # rack_id is free-form text (rack codenames like "rpg93"), not a number.
    cfg = prov.build_config("MAC", {"rack_id": "rpg93", "role": "Primary"})
    assert cfg == {
        "message_type": "config",
        "mac": "MAC",
        "configured": True,
        "enabled": True,
        "rack_id": "rpg93",
        "role": "Primary",
    }


def test_build_config_missing_key_raises_keyerror():
    with pytest.raises(KeyError):
        prov.build_config("MAC", {"role": "Primary"})  # no rack_id


# --- get_device_state ---------------------------------------------------------

def test_get_device_state_maps_rows(monkeypatch, cursor_conn):
    conn, cur = cursor_conn
    cur.fetchall.return_value = [("MAC1", "v0.0.2"), ("MAC2", "v0.0.3")]
    monkeypatch.setattr(prov, "conn", conn)
    assert prov.get_device_state() == {
        "MAC1": {"firmware_version": "v0.0.2"},
        "MAC2": {"firmware_version": "v0.0.3"},
    }


def test_get_device_state_returns_empty_on_error(monkeypatch, cursor_conn):
    conn, cur = cursor_conn
    cur.execute.side_effect = Exception("db down")
    monkeypatch.setattr(prov, "conn", conn)
    assert prov.get_device_state() == {}


# --- upsert_device_state ------------------------------------------------------

def test_upsert_device_state_runs_upsert(monkeypatch, cursor_conn):
    conn, cur = cursor_conn
    monkeypatch.setattr(prov, "conn", conn)
    prov.upsert_device_state("MAC", "v1.0")
    cur.execute.assert_called_once()
    sql, params = cur.execute.call_args.args
    assert "INSERT INTO repacss_environment.current_status" in sql
    assert "ON CONFLICT (mac) DO UPDATE" in sql
    assert params == ("MAC", "v1.0")


def test_upsert_device_state_swallows_error(monkeypatch, cursor_conn):
    conn, cur = cursor_conn
    cur.execute.side_effect = Exception("boom")
    monkeypatch.setattr(prov, "conn", conn)
    prov.upsert_device_state("MAC", "v1.0")  # must not raise


# --- on_connect ---------------------------------------------------------------

def test_on_connect_subscribes_to_hello():
    client = MagicMock()
    prov.on_connect(client, None, None, 0, None)
    client.subscribe.assert_called_once_with("repacss/devices/+/hello", qos=1)


# --- on_message ---------------------------------------------------------------

def test_on_message_known_device_publishes_config(monkeypatch, make_msg):
    monkeypatch.setattr(prov, "upsert_device_state", MagicMock())
    monkeypatch.setattr(
        prov.device_registry, "lookup",
        MagicMock(return_value={"rack_id": "rpg93", "role": "Primary"}),
    )
    client = MagicMock()
    msg = make_msg(
        "repacss/devices/ECE3347C07D0/hello",
        {"message_type": "hello", "mac": "ECE3347C07D0", "firmware_version": "v0.0.2"},
    )

    prov.on_message(client, None, msg)

    prov.upsert_device_state.assert_called_once_with("ECE3347C07D0", "v0.0.2")
    client.publish.assert_called_once()
    topic, payload = client.publish.call_args.args[0], client.publish.call_args.args[1]
    assert topic == "repacss/devices/ECE3347C07D0/config"
    body = json.loads(payload)
    assert body["configured"] is True
    assert body["role"] == "Primary"


def test_on_message_unknown_device_publishes_not_configured(monkeypatch, make_msg):
    monkeypatch.setattr(prov, "upsert_device_state", MagicMock())
    monkeypatch.setattr(prov.device_registry, "lookup", MagicMock(return_value=None))
    client = MagicMock()
    msg = make_msg(
        "repacss/devices/AABBCCDDEEFF/hello",
        {"message_type": "hello", "mac": "AABBCCDDEEFF"},
    )

    prov.on_message(client, None, msg)

    body = json.loads(client.publish.call_args.args[1])
    assert body["configured"] is False
    assert body["reason"] == "unknown mac"


def test_on_message_invalid_json_does_nothing(monkeypatch, make_msg):
    monkeypatch.setattr(prov, "upsert_device_state", MagicMock())
    client = MagicMock()
    msg = make_msg("repacss/devices/ECE3347C07D0/hello", "not-json{")

    prov.on_message(client, None, msg)

    client.publish.assert_not_called()
    prov.upsert_device_state.assert_not_called()
