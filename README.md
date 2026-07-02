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
├── docker-compose.yml                     # the 5-service stack
├── prometheus/
│   ├── prometheus.yml                     # scrape config (snmp_exporter relabel dance)
│   └── alert.rules.yml                    # InterfaceDown + ConfigDrift
├── alertmanager/
│   ├── alertmanager.yml                   # routing + two optional notifiers (webhook, email)
│   └── secrets/                           # gitignored: webhook_url / smtp_password files
├── snmp_exporter/
│   ├── snmp.yml                           # gitignored: generated, real community string
│   └── generator/
│       ├── generator.yml                  # if_mib + cisco_cpu module definitions
│       ├── fetch-mibs.sh                  # downloads the MIBs generator.yml needs
│       └── mibs/                          # gitignored: fetched MIB source files
├── scripts/
│   └── export_config_drift.py             # config-audit report JSON -> Prometheus textfile
├── textfile_collector/                    # node_exporter reads *.prom files here
└── grafana/
    ├── provisioning/                      # auto-wires the datasource + dashboards
    └── dashboards/network-overview.json   # interface throughput in/out, CPU, config drift
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

## Notifications

`alertmanager.yml` ships with two notifiers defined but commented out — a generic
webhook and email via SMTP. Both are wired as **file-based secrets** (`url_file`,
`auth_password_file`), so the committed config never contains a literal webhook URL
or password; only a path to a file under `alertmanager/secrets/` (gitignored).
Alertmanager re-reads these files on each send, so rotating a secret is just
overwriting the file — no restart needed.

To enable one (or both):

1. `mkdir -p alertmanager/secrets` (already gitignored via `alertmanager/secrets/*`).
2. Generic webhook: write the endpoint URL to `alertmanager/secrets/webhook_url`,
   uncomment the `webhook_configs` block in `alertmanager.yml`.
   Email: write the SMTP password to `alertmanager/secrets/smtp_password`, uncomment
   the `email_configs` block and fill in `to`/`from`/`smarthost`/`auth_username`.
3. Uncomment the `alertmanager/secrets` volume mount in `docker-compose.yml`'s
   `alertmanager` service.
4. `docker compose up -d alertmanager` (or restart the whole stack).

**How this was validated without real gear or real secrets:** the webhook path was
tested end-to-end locally — a throwaway Alertmanager container plus a local HTTP
listener on the same Docker network (no external destination), fed a synthetic
`ConfigDrift` alert via `POST /api/v2/alerts` using RFC 5737 test values
(`device="TESTDEV"`, `ip="192.0.2.1"`), matching exactly the label shape
`export_config_drift.py` produces from a real drift finding. Alertmanager's own log
confirmed `"Notify success"` after retrying the webhook. Email isn't verifiable the
same way (it needs a real mailbox + SMTP relay), so that path is config-checked
(`docker compose config --quiet` / Alertmanager's own startup validation) but not
delivery-tested — worth doing once real SMTP credentials exist.

## Adding CPU

Interface metrics come from the standard `if_mib` module. Cisco CPU lives in
`CISCO-PROCESS-MIB` (`cpmCPUTotal5minRev`), which the bundled module doesn't include.
The dashboard panel already queries `cpmCPUTotal5minRev`, so it populates the moment
that metric exists — this section is what makes it exist.

`snmp_exporter/generator/` has everything needed to build a custom `snmp.yml`:

- `generator.yml` — two modules: `if_mib` (copied verbatim from snmp_exporter's own
  upstream default, so interface metrics aren't lost) and `cisco_cpu` (new, walks
  `CISCO-PROCESS-MIB::cpmCPUTotal5minRev`).
- `fetch-mibs.sh` — downloads the MIB files both modules need (Cisco's own
  [cisco-mibs](https://github.com/cisco/cisco-mibs) repo, pinned to a specific commit,
  plus the standard IETF/net-snmp base MIBs). MIBs aren't vendored into the repo
  (large, third-party, easy to re-fetch) — `snmp_exporter/generator/mibs/` is
  gitignored.

To generate and wire it in:

```bash
cd snmp_exporter/generator
./fetch-mibs.sh
docker run --rm -v "$(pwd)":/opt prom/snmp-generator:v0.30.1 generate
mv snmp.yml ../snmp.yml
```

Then, if your community string isn't `public`, edit the `auths.public_v2.community`
in `generator.yml` before regenerating (never commit a real community string —
`snmp_exporter/snmp.yml` is gitignored for exactly that reason). Finally:

1. Uncomment the `snmp.yml` volume mount in `docker-compose.yml`'s `snmp_exporter`
   service.
2. Add `cisco_cpu` to `prometheus.yml`'s `snmp-cisco` job: `module: [if_mib, cisco_cpu]`.
3. `docker compose up -d`.

**What's verified vs. not:** the generator run above is real — it downloaded the
actual MIBs, parsed them, and produced a working `snmp.yml` whose `if_mib` module was
diffed against snmp_exporter's own bundled default and confirmed equivalent (same 39
metrics/OIDs; the only difference is a handful of newer IANA interface-type enum
values, since `fetch-mibs.sh` pulls the current IANA list rather than net-snmp's
older bundled copy — additive, not a regression). The `cisco_cpu` module correctly
resolves to OID `1.3.6.1.4.1.9.9.109.1.1.1.1.8` as a gauge indexed by
`cpmCPUTotalIndex`. What's **not** verified: an actual value coming back from real
Cisco gear — that still needs live hardware and is part of the weekend-one milestone
above, not something to fake with a fixture.

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

### Where this could go further

The natural next step — the dashboard explaining *why* something's down, not
just *that* it is, by correlating an `InterfaceDown` alert with a recent
config-audit drift into a plain-English root cause — is real, but it's an LLM
reasoning task, not something to hand-code into Grafana/Prometheus. It's
already the next stage of this platform, in progress in a private repo, gated
on some knowledge-base groundwork that isn't done yet. Auto-remediation (a
tool applying a recommended fix) is a separate, later step, and always stays
human-gated — this pillar doesn't do that directly. What's here today is the
piece that's actually available without any of that: the drifted device's
management IP directly in the alert, so a human can go fix it by hand.
[Message me on LinkedIn](https://www.linkedin.com/in/stefan-c-reed/) if you
want to know more about where this is headed.

## Status

🚧 Image tags pinned to specific versions (prometheus v3.13.0, alertmanager v0.33.0,
snmp-exporter v0.30.1, grafana 13.0.3). Verified via `docker compose up`: all four
services pull and start cleanly, all report healthy, and Prometheus correctly relays
through snmp_exporter's relabel dance. Still unverified against live SNMP — that's the
weekend-one milestone above, waiting on real device IPs and a working community string.
