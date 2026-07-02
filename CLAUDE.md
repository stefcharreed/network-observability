# CLAUDE.md — network-observability

Pillar 4 of the NetDevOps platform: Prometheus + Alertmanager + snmp_exporter + Grafana,
as code. **No package/code dependency on config-audit** — this repo installs and runs
with nothing from `netmiko-config-audit` present. It does now have one **data-contract**
dependency: `scripts/export_config_drift.py` reads config-audit's `report` JSON output
AND its `config.yaml` device list by shape (not by importing its code) to expose drift
+ management IP as a metric. See "Wiring in config-audit drift" in README.

## Commands
- Up: `docker compose up -d`   ·   Down: `docker compose down`
- Health: Prometheus :9090 (Status → Targets) · Grafana :3000 · Alertmanager :9093
- Drift export (run after `config-audit report`, same cron job; use config-audit's own
  venv python so PyYAML is already present):
  `.venv/bin/python3 scripts/export_config_drift.py <report dir> <config.yaml path> ./textfile_collector`

## Layout
- `docker-compose.yml` — the 5-service stack (prometheus, alertmanager, snmp_exporter,
  node_exporter, grafana)
- `prometheus/prometheus.yml` — scrape config (snmp_exporter relabel dance +
  node_exporter for the textfile collector)
- `prometheus/alert.rules.yml` — alert rules (InterfaceDown, ConfigDrift)
- `alertmanager/alertmanager.yml` — routing + two optional notifiers (webhook, email),
  both wired via file-based secrets under `alertmanager/secrets/` (gitignored)
- `snmp_exporter/generator/` — `generator.yml` (if_mib + cisco_cpu modules) and
  `fetch-mibs.sh` (downloads the MIBs both need); `snmp_exporter/generator/mibs/` and
  `snmp_exporter/snmp.yml` are gitignored (large third-party download / real
  community string, respectively) — see README's "Adding CPU"
- `grafana/provisioning/` + `grafana/dashboards/` — auto-provisioned datasource + dashboard
- `scripts/export_config_drift.py` — config-audit report JSON + config.yaml → Prometheus
  textfile format (drift metric labeled with device name + management IP)
- `textfile_collector/` — where the script writes; node_exporter reads `*.prom` files here

## Rules
- **Never commit secrets.** Grafana admin password comes from a gitignored `.env`
  (`GRAFANA_ADMIN_PASSWORD`); `.env.example` shows the shape. Never a literal password
  in `docker-compose.yml`.
- **Alertmanager notifier secrets use file-based refs, not env vars.** Alertmanager's
  config format has no `${VAR}` substitution (unlike Grafana's env-driven password),
  so `alertmanager.yml` points at `url_file`/`auth_password_file` paths under
  `alertmanager/secrets/` (gitignored, `docker-compose.yml`'s mount for it is
  commented out by default) instead. Verified 2026-07-01: a throwaway Alertmanager
  container + local HTTP listener on one Docker network, fed a synthetic `ConfigDrift`
  alert via the API with RFC 5737 test values, confirmed real webhook delivery
  ("Notify success" in Alertmanager's log). Don't switch this to literal secrets in
  the yaml or to compose-level env substitution — Alertmanager doesn't support the
  latter.
- **Image tags are pinned to specific versions** (checked 2026-07-01: prometheus
  v3.13.0, alertmanager v0.33.0, snmp-exporter v0.30.1, node-exporter v1.11.1,
  grafana 13.0.3), not `:latest`. Re-verify and re-pin deliberately if you ever bump
  these — don't drift back to `:latest`.
- **`snmp_exporter/generator/generator.yml`'s `if_mib` module must stay a byte-for-byte
  copy of upstream's** (from `prometheus/snmp_exporter`'s own `generator/generator.yml`
  at the pinned `v0.30.1` tag) — a custom `snmp.yml` replaces the exporter's bundled
  default entirely, so if `if_mib` drifts from upstream, interface metrics silently
  change shape. Verified 2026-07-01: generated output's `if_mib` module diffed
  field-for-field against the image's own bundled default and confirmed equivalent
  (identical 39 metrics/OIDs; only difference was 5 newer IANA ifType enum values,
  additive not breaking). `cisco_cpu` (new) resolves to
  `CISCO-PROCESS-MIB::cpmCPUTotal5minRev`, OID `1.3.6.1.4.1.9.9.109.1.1.1.1.8` — this
  is generator-verified only, **not tested against real hardware** (no live gear to
  confirm an actual value comes back). Don't upgrade `prom/snmp-generator`'s pinned
  tag without re-diffing `if_mib` the same way.
- **`export_config_drift.py` writes atomically** (temp file + rename) — node_exporter's
  textfile collector can otherwise scrape a half-written `.prom` file mid-write. Keep
  this pattern if you touch the script.
- **`ConfigDrift` has no `for:` debounce, unlike `InterfaceDown`.** A drift finding is
  already a discrete, one-shot result from a completed `config-audit diff` run, not a
  noisy raw counter that flaps — there's nothing to debounce. Don't add a `for:` here
  by reflexive analogy to the interface alert; it would just delay a real finding.
- **`ConfigDrift` fires per-device (`config_audit_device_drift == 1`), not on the
  aggregate `config_audit_devices_drifted` count.** Deliberate: firing per series puts
  `{{ $labels.device }}` and `{{ $labels.ip }}` directly in the alert annotation, so
  the alert itself tells you where to go, not just how many devices need attention.
  Don't switch this back to the aggregate metric without preserving that.
- **AI-summary correlation (e.g. "interface down, likely due to a recent VLAN change")
  and auto-remediation are deliberately NOT built here.** That's Platform Stage 3 /
  `network-troubleshooting-agent`'s job (LLM + MCP retrieval, not hand-coded
  correlation), gated on skill-catalog coverage that doesn't exist yet. Auto-pushing a
  fix to a device is the separate, later, human-gated "Closed-loop remediation" pillar
  (`DEFERRED`). Don't build either into this repo's Grafana/Prometheus config — see
  README's "Where this could go further".
- **CI (`.github/workflows/validate.yml`) brings the whole stack up on every push/PR**
  and checks all four services report healthy, plus that the `snmp-cisco` job is
  registered in Prometheus (it's expected to be `down`/`unknown` in CI — no real
  device reachable from a GitHub runner — this only proves the wiring, not live SNMP).
  Live-hardware validation (a real target going green) is still a manual, local step.
- The deliverable that matters is **one tuned alert** — the documented false-positive →
  fix (naive `ifOperStatus == 2` → add `and ifAdminStatus == 1` + `for: 2m`) — not a
  wall of dashboards. The tuning write-up IS the interview answer.
