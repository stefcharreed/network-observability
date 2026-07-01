#!/usr/bin/env python3
"""Convert the latest netmiko-config-audit JSON report into Prometheus
textfile-collector format, so node_exporter can expose config drift as a
metric alongside the SNMP data -- config drift IS "actual behavior over time",
exactly Pillar 4's charter, sitting next to interface throughput and CPU.

Run this right after `config-audit report` (same cron job) -- see README's
"Wiring in config-audit drift" section.

This is a data-contract dependency on config-audit's report JSON shape
(devices_total/devices_ok/devices_failed/drifted/failures), not a code or
package dependency -- this repo still needs no config-audit install to run.
If that JSON schema ever changes, this script needs updating to match; see
CLAUDE.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _latest_report(report_dir: Path) -> Path | None:
    reports = sorted(report_dir.glob("run-*.json"))
    return reports[-1] if reports else None


def _render_metrics(report: dict) -> str:
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
        "# HELP config_audit_device_drift Devices with detected config drift "
        "(only present for drifted devices -- absence means in sync)",
        "# TYPE config_audit_device_drift gauge",
    ]
    for device in sorted(drifted):
        lines.append(f'config_audit_device_drift{{device="{device}"}} 1')
    return "\n".join(lines) + "\n"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: export_config_drift.py <config_audit_report_dir> <textfile_collector_dir>")
        return 2
    report_dir, textfile_dir = Path(sys.argv[1]), Path(sys.argv[2])

    latest = _latest_report(report_dir)
    if latest is None:
        print(f"no run-*.json reports found in {report_dir}")
        return 1

    report = json.loads(latest.read_text(encoding="utf-8"))
    metrics = _render_metrics(report)

    textfile_dir.mkdir(parents=True, exist_ok=True)
    # Write to a temp file then atomically rename -- node_exporter's textfile
    # collector can otherwise scrape a half-written file mid-write.
    tmp = textfile_dir / "config_audit_drift.prom.tmp"
    tmp.write_text(metrics, encoding="utf-8")
    tmp.rename(textfile_dir / "config_audit_drift.prom")
    print(f"wrote metrics from {latest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
