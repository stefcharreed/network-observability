# Observability stack (Pillar 4)

> [![validate](https://github.com/stefcharreed/network-observability/actions/workflows/validate.yml/badge.svg)](https://github.com/stefcharreed/network-observability/actions/workflows/validate.yml)

Prometheus + Alertmanager + snmp_exporter + Grafana, as code, for monitoring the
Cisco gear. This is **Pillar 4** of the platform — the "actual behavior over time"
layer that sits alongside Project 1's "intended vs actual config" layer.

> **Why build it by hand instead of a turnkey NMS.** A GUI NMS auto-discovers your
> devices and hands you dashboards — which means you learn nothing transferable. This
> stack forces you to write the scrape config, the PromQL, and the alert rules
> yourself. The setup *is* the payoff: it's hands-on PromQL and alerting-as-code, and
> the threshold-tuning exercise below is a ready-made interview answer.

## What's here

```
observability/
├── docker-compose.yml                     # the 4-service stack
├── prometheus/
│   ├── prometheus.yml                     # scrape config (snmp_exporter relabel dance)
│   └── alert.rules.yml                    # one alert: InterfaceDown
├── alertmanager/
│   └── alertmanager.yml                   # routing (no notifier wired yet)
└── grafana/
    ├── provisioning/                      # auto-wires the datasource + dashboards
    └── dashboards/network-overview.json   # interface throughput in/out + CPU
```

## The weekend-one milestone

The goal for the first sitting is small and complete — not a sprawling NMS:

1. `docker compose up -d` on the i7 Linux side.
2. Edit `prometheus/prometheus.yml`: replace the two placeholder `192.0.2.x` IPs with
   your real ISR/Catalyst management IPs.
3. Point snmp_exporter at your community string. The bundled `if_mib` module +
   `public_v2` auth works out of the box for interface counters; if your community
   isn't `public`, generate an `snmp.yml` and mount it (see the commented block in
   `docker-compose.yml`).
4. Open Prometheus at `http://<host>:9090` → Status → Targets. The `snmp-cisco` job
   should go green. If not, the Targets page tells you exactly why (auth, timeout,
   unreachable).
5. Open Grafana at `http://<host>:3000` (admin / admin, change it). The **Network
   Overview** dashboard is auto-provisioned: interface throughput in/out should be
   live. (The CPU panel stays "No data" until you add the Cisco MIB module — see
   below.)

That's the milestone: **one dashboard with live interface throughput, and one alert
rule loaded.** Stop there. Resist adding ten more panels.

## The tuning exercise

The whole point of `alert.rules.yml` is to *deliberately* get the alert wrong, then
fix it, and document the before/after. Do it in this order:

1. **Start naive.** Temporarily change the rule to the obvious-but-wrong form:
   ```yaml
   expr: ifOperStatus == 2
   for: 0s
   ```
   Reload Prometheus. Watch it fire `InterfaceDown` for **every shut/unused port** on
   the gear — a flood of false positives. This is what a naive threshold does.
2. **Fix the threshold logic.** Add the admin-status filter so you only alert on ports
   that are *supposed* to be up:
   ```yaml
   expr: ifOperStatus == 2 and ifAdminStatus == 1
   ```
   The flood stops — only genuinely-down-but-enabled links alert.
3. **Fix the flapping.** Add `for: 2m` so a 10-second link blip during, say, a switch
   reload doesn't page you; the interface has to stay down for two minutes.
4. **Document before/after.** Screenshot the alert list before (flooded) and after
   (clean), and write one paragraph: *"Naive `ifOperStatus == 2` produced N false
   positives from admin-down ports; adding `and ifAdminStatus == 1` plus `for: 2m`
   eliminated them while preserving real link-down detection."* That paragraph is a
   better answer to "tell me about alerting you've tuned" than anything memorized.

The committed `alert.rules.yml` is already at the **end state** (step 2 + 3), so the
repo shows the good version; the exercise is about understanding *why* it's the good
version by breaking it first.

## Adding CPU (the documented next step)

Interface metrics come from the standard `if_mib` module. Cisco CPU lives in
`CISCO-PROCESS-MIB` (`cpmCPUTotal5minRev`), which the bundled module doesn't include.
To light up the CPU panel: install the snmp_exporter generator, add a Cisco module
that walks that OID, regenerate `snmp.yml`, mount it (compose comment block), and add
`cisco_cpu` to the scrape `module:` list. The dashboard panel already queries
`cpmCPUTotal5minRev`, so it populates the moment that metric exists.

## Platform seam

This stack shares the platform's single source of device truth: the same
`inventory.yaml` Project 1 uses should eventually generate the `prometheus.yml`
target list, so you add a device once. That generator is a small follow-up — for now
the target list is hand-maintained, and that's fine for two devices.

## Wiring in config-audit drift

Config drift is itself "actual behavior over time" — the same charter as interface
throughput and CPU — so it shows up on this dashboard too, not just in
`netmiko-config-audit`'s own terminal output.

`scripts/export_config_drift.py` reads the latest `run-*.json` report
`netmiko-config-audit`'s `report` command writes, plus its `config.yaml` device
list (for each drifted device's management IP), and converts both into Prometheus
textfile-collector format for `node_exporter` to pick up. Run it right after
`config-audit report` in the same cron job, using config-audit's own venv
interpreter so PyYAML is already available:

```cron
0 2 * * *  cd /opt/netmiko-config-audit && .venv/bin/config-audit report \
  && .venv/bin/python3 /opt/network-observability/scripts/export_config_drift.py \
       /path/to/netmiko-config-private/reports \
       /opt/netmiko-config-audit/config/config.yaml \
       /opt/network-observability/textfile_collector
```

This is a **data-contract** dependency on config-audit's report JSON shape
(`devices_total`/`devices_drifted`/etc.) and its `config.yaml` device list
(`name`/`host`), not a code or package dependency — this repo still needs no
config-audit install to run standalone. If either shape ever changes,
`export_config_drift.py` needs updating to match.

### If drift fires

The `ConfigDrift` alert and the dashboard's "Drifted Devices" table don't just say
*that* something changed — each drifted device is labeled with its management IP
(`config_audit_device_drift{device="ISR1", ip="172.31.16.52"}`), so the alert
itself tells you where to go, not just that something needs attention:

1. **See what changed.** Run `config-audit diff` — it shows the exact unified diff
   for every drifted device, not just that one exists.
2. **Decide if it was authorized.** Was this a planned/approved change, or
   unexpected?
3. **Authorized:** run `config-audit promote <device>` — reviews the diff again,
   requires your explicit confirmation, and accepts the new state as the baseline.
4. **Unauthorized:** SSH to the IP shown in the alert and revert the device's
   config by hand (this platform doesn't push config changes yet — closed-loop
   remediation is a deferred, separate pillar, see `network-platform-docs`), then
   re-run `config-audit backup` and confirm `diff` shows clean.
5. The alert clears on its own next cron cycle once the device's
   `config_audit_device_drift` series disappears (in sync again) — no manual
   alert-silencing needed.

### Where this could go further (not built — see network-platform-docs)

The natural next step — "the dashboard says *why* it's down, not just *that* it
is" (e.g. correlating an `InterfaceDown` alert with a recent config-audit drift on
the same device into a plain-English summary) — is real, but it's an LLM
reasoning task, not something to hand-code into Grafana/Prometheus. That's
**Platform Stage 3**, already scoped in the private `network-troubleshooting-agent`
repo: an MCP client with both `config-audit`'s MCP server and a troubleshooting-
knowledge MCP server registered, correlating alerts + drift + domain knowledge
into a hypothesis. It's gated on CCNP skill-catalog coverage that doesn't exist
yet (see `network-platform-docs/DECISIONS.md` D20/D21) — not something to build
here. Auto-remediation (a tool pushing a fix to the device based on that
hypothesis) is a separate, later, explicitly human-gated step
(`network-platform-docs/roadmap.md` item 9, "Closed-loop remediation" —
`DEFERRED`): propose → Batfish-validate → human approve → push → verify →
rollback. The IP-in-the-alert piece above is the whole "surface it for a human to
go fix by hand" step done today, with none of that machinery.

## Status

🚧 Image tags pinned to specific versions (prometheus v3.13.0, alertmanager v0.33.0,
snmp-exporter v0.30.1, grafana 13.0.3). Verified via `docker compose up`: all four
services pull and start cleanly, all report healthy, and Prometheus correctly relays
through snmp_exporter's relabel dance. Still unverified against live SNMP — that's the
weekend-one milestone above, waiting on real device IPs and a working community string.
