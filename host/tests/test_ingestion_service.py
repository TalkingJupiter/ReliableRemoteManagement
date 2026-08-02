"""Tests for app.ingestion_service.

Functions covered and their cases:

on_connect(...)
- Subscribes to the four device topics (telemetry, status, event, ack).

is_registered(mac)
- True when device_map has a matching row, False when it does not.

rack_filter(mac)
- Returns the rack_id when found, None when the device is not in device_map.

handle_telemetry(conn, ...)
- Inserts one telemetry row with the given parameters.

handle_status / handle_event / handle_ack
- Currently placeholders that raise NotImplementedError (documents current state).

on_message(...)
- Unregistered device -> ignored (no telemetry handling).
- Telemetry -> one handle_telemetry call per sensor reading across all buses.
- Unknown message type -> warns.
- Invalid JSON -> ignored.
- SHARP EDGE: telemetry payload with no 'sensors' item currently raises
  StopIteration (unguarded next(...)); documented so it is not lost.
"""

from unittest.mock import MagicMock

import pytest

import app.ingestion_service as ing


# --- on_connect ---------------------------------------------------------------

def test_on_connect_subscribes_all_device_topics():
    client = MagicMock()
    ing.on_connect(client, None, None, 0, None)
    subscribed = {call.args[0] for call in client.subscribe.call_args_list}
    assert subscribed == {
        "repacss/devices/+/telemetry",
        "repacss/devices/+/status",
        "repacss/devices/+/event",
        "repacss/devices/+/ack",
    }


# --- is_registered ------------------------------------------------------------

def test_is_registered_true_when_row(monkeypatch, cursor_conn):
    conn, cur = cursor_conn
    cur.fetchone.return_value = (1,)
    monkeypatch.setattr(ing, "conn", conn)
    assert ing.is_registered("MAC") is True


def test_is_registered_false_when_none(monkeypatch, cursor_conn):
    conn, cur = cursor_conn
    cur.fetchone.return_value = None
    monkeypatch.setattr(ing, "conn", conn)
    assert ing.is_registered("MAC") is False


# --- rack_filter --------------------------------------------------------------

def test_rack_filter_returns_rack(monkeypatch, cursor_conn):
    conn, cur = cursor_conn
    cur.fetchone.return_value = (7,)
    monkeypatch.setattr(ing, "conn", conn)
    assert ing.rack_filter("MAC") == 7


def test_rack_filter_none_when_missing(monkeypatch, cursor_conn):
    conn, cur = cursor_conn
    cur.fetchone.return_value = None
    monkeypatch.setattr(ing, "conn", conn)
    assert ing.rack_filter("MAC") is None


# --- handle_telemetry ---------------------------------------------------------

def test_handle_telemetry_inserts_row(cursor_conn):
    conn, cur = cursor_conn
    ing.handle_telemetry(conn, "2026-01-01T00:00:00Z", "MAC", 1, "inlet", 0, 25.5)
    cur.execute.assert_called_once()
    sql, params = cur.execute.call_args.args
    assert "INSERT INTO repacss_environment.telemetry" in sql
    assert params == ("2026-01-01T00:00:00Z", "MAC", 1, "inlet", 0, 25.5)


# --- unimplemented handlers ---------------------------------------------------

@pytest.mark.parametrize("fn_name", ["handle_status", "handle_event", "handle_ack"])
def test_unimplemented_handlers_raise(fn_name):
    with pytest.raises(NotImplementedError):
        getattr(ing, fn_name)("MAC", {})


# --- on_message ---------------------------------------------------------------

def test_on_message_ignores_unregistered(monkeypatch, make_msg):
    monkeypatch.setattr(ing, "is_registered", lambda mac: False)
    ht = MagicMock()
    monkeypatch.setattr(ing, "handle_telemetry", ht)
    msg = make_msg("repacss/devices/MAC/telemetry", {"items": []})

    ing.on_message(None, None, msg)

    ht.assert_not_called()


def test_on_message_telemetry_calls_handle_per_sensor(monkeypatch, make_msg):
    monkeypatch.setattr(ing, "is_registered", lambda mac: True)
    monkeypatch.setattr(ing, "rack_filter", lambda mac: 1)
    ht = MagicMock()
    monkeypatch.setattr(ing, "handle_telemetry", ht)

    payload = {"items": [
        {"kind": "heartbeat"},
        {"kind": "sensors", "buses": [
            {"bus": "inlet", "temperatures_c": [25.0, None, 26.0]},
            {"bus": "exhaust", "temperatures_c": [30.0]},
        ]},
    ]}
    msg = make_msg("repacss/devices/MAC/telemetry", payload)

    ing.on_message(None, None, msg)

    # 3 inlet readings + 1 exhaust reading = 4 rows.
    assert ht.call_count == 4
    first = ht.call_args_list[0].args   # (conn, ts, mac, rack_id, bus, sensor_index, temp)
    assert first[2] == "MAC"
    assert first[3] == 1
    assert first[4] == "inlet"
    assert first[5] == 0
    assert first[6] == 25.0


def test_on_message_unknown_type_warns(monkeypatch, make_msg, capsys):
    monkeypatch.setattr(ing, "is_registered", lambda mac: True)
    msg = make_msg("repacss/devices/MAC/wat", {"x": 1})

    ing.on_message(None, None, msg)

    assert "Unknown message type" in capsys.readouterr().out


def test_on_message_invalid_json_ignored(monkeypatch, make_msg):
    monkeypatch.setattr(ing, "is_registered", lambda mac: True)
    ht = MagicMock()
    monkeypatch.setattr(ing, "handle_telemetry", ht)
    msg = make_msg("repacss/devices/MAC/telemetry", "not-json{")

    ing.on_message(None, None, msg)

    ht.assert_not_called()


def test_on_message_telemetry_without_sensors_raises_stopiteration(monkeypatch, make_msg):
    # DOCUMENTS CURRENT BEHAVIOUR / SHARP EDGE: the unguarded next(...) that finds
    # the 'sensors' item raises StopIteration when there is no such item. Worth
    # guarding with a default in the code; captured here so the behaviour is explicit.
    monkeypatch.setattr(ing, "is_registered", lambda mac: True)
    monkeypatch.setattr(ing, "rack_filter", lambda mac: 1)
    msg = make_msg("repacss/devices/MAC/telemetry", {"items": [{"kind": "heartbeat"}]})

    with pytest.raises(StopIteration):
        ing.on_message(None, None, msg)
