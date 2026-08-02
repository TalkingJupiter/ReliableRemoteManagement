CREATE SCHEMA IF NOT EXISTS repacss_environment;
CREATE TABLE IF NOT EXISTS repacss_environment.device_map (
    mac macaddr PRIMARY KEY,
    rack_id int NOT NULL,
    role text NOT NULL,
    enabled boolean NOT NULL,
    retired boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS repacss_environment.telemetry (
    ts_host timestamptz NOT NULL,
    mac macaddr NOT NULL,
    rack_id int NOT NULL,
    bus text NOT NULL CHECK (bus IN ('inlet', 'exhaust')),
    sensor_index smallint NOT NULL,
    temperature_celsius real
);
SELECT create_hypertable('repacss_environment.telemetry', 'ts_host');

CREATE TABLE IF NOT EXISTS repacss_environment.events (
    ts_host timestamptz NOT NULL,
    mac macaddr NOT NULL,
    event_type text NOT NULL,
    details text,
    rack_id int NOT NULL,
    role text NOT NULL
);
SELECT create_hypertable('repacss_environment.events', 'ts_host');

CREATE TABLE IF NOT EXISTS repacss_environment.current_status(
    mac macaddr PRIMARY KEY,
    alive boolean NOT NULL,
    last_seen timestamptz NOT NULL,
    last_ip INET,
    running_firmware_version text NOT NULL
);

CREATE TABLE IF NOT EXISTS repacss_environment.alerts (
    ts_host timestamptz NOT NULL,
    source text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('info', 'warning', 'critical', 'error')),
    alert_type text NOT NULL,
    details text,
    resolved boolean NOT NULL
);

CREATE TABLE IF NOT EXISTS repacss_environment.unknown_devices (
    mac macaddr PRIMARY KEY,
    first_seen timestamptz NOT NULL,
    last_seen timestamptz NOT NULL,
    message_count_24h int NOT NULL
);