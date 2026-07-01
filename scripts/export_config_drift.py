#!/usr/bin/env python3
"""Convert the latest netmiko-config-audit JSON report into Prometheus
textfile-collector format, so node_exporter can expose config drift as a
metric alongside the SNMP data -- config drift IS "actual behavior over time",
exactly Pillar 4's charter, sitting next to interface throughput and CPU.

Run this right after `config-audit report` (same cron job) -- see README's
"Wiring in config-audit drift" section. Run it with config-audit's own venv
interpreter (e.g. /opt/netmiko-config-audit/.venv/bin/python3) so PyYAML is
already available -- this script doesn't ship its own dependency management.

This is a data-contract dependency on config-audit's report JSON shape
(devices_total/devices_ok/devices_failed/drifted/failures) AND its
config.yaml device list (name/host), not a code or package dependency --
this repo still needs no config-audit install to run. If either shape
changes, this script needs updating to match; see CLAUDE.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


def _latest_report(report_dir: Path) -> Path | None:
    reports = sorted(report_dir.glob("run-*.json"))
    return reports[-1] if reports else None


def _device_ips(config_path: Path) -> dict[str, str]:
    """Read config-audit's config.yaml and return {device_name: host}.

    Used to label the drift metric with the device's management IP -- so
    "which device drifted" comes with "where do I SSH to fix it" for free,
    on the dashboard and in the alert annotation, without a human having to
    cross-reference config.yaml by hand.
    """
    if not config_path.exists():
        return {}
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return {
        d["name"]: d["host"]
        for d in raw.get("devices", [])
        if "name" in d and "host" in d
    }


def _render_metrics(report: dict, device_ips: dict[str, str]) -> str:
    drifted = report.get("drifted", [])
    failures = report.get("failures", {})

    lines = [
        "# HELP config_audit_devices_total Total devices tracked by config-audit",
        "# TYPE config_audit_devices_total gauge",
        f"config_audit_devices_total {report.get('devices_total', 0)}",
        "# HELP config_audit_devices_drifted Number of devices with detected config drift",
        "# TYPE config_audit_devices_drifted gauge",
        f"config_audit_devices_drifted {len(drifted)}",
        "# HELP config_audit_devices_failed Number of devices that failed to collect",
        "# TYPE config_audit_devices_failed gauge",
        f"config_audit_devices_failed {len(failures)}",
        "# HELP config_audit_device_drift Devices with detected config drift, "
        "labeled with their management IP (only present for drifted devices -- "
        "absence means in sync)",
        "# TYPE config_audit_device_drift gauge",
    ]
    for device in sorted(drifted):
        ip = device_ips.get(device, "")
        lines.append(f'config_audit_device_drift{{device="{device}",ip="{ip}"}} 1')
    return "\n".join(lines) + "\n"


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "usage: export_config_drift.py <config_audit_report_dir> "
            "<config_audit_config_yaml> <textfile_collector_dir>"
        )
        return 2
    report_dir = Path(sys.argv[1])
    config_path = Path(sys.argv[2])
    textfile_dir = Path(sys.argv[3])

    latest = _latest_report(report_dir)
    if latest is None:
        print(f"no run-*.json reports found in {report_dir}")
        return 1

    report = json.loads(latest.read_text(encoding="utf-8"))
    device_ips = _device_ips(config_path)
    metrics = _render_metrics(report, device_ips)

    textfile_dir.mkdir(parents=True, exist_ok=True)
    # Write to a temp file then atomically rename -- node_exporter's textfile
    # collector can otherwise scrape a half-written file mid-write.
    tmp = textfile_dir / "config_audit_drift.prom.tmp"
    tmp.write_text(metrics, encoding="utf-8")
    tmp.rename(textfile_dir / "config_audit_drift.prom")
    print(f"wrote metrics from {latest} (device IPs from {config_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
