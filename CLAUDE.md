# CLAUDE.md — network-observability

Pillar 4 of the NetDevOps platform: Prometheus + Alertmanager + snmp_exporter + Grafana,
as code. **No package/code dependency on config-audit** — this repo installs and runs
with nothing from `netmiko-config-audit` present. It does now have one **data-contract**
dependency: `scripts/export_config_drift.py` reads config-audit's `report` JSON output
by shape (not by importing its code) to expose drift as a metric. See "Wiring in
config-audit drift" in README.

## Commands
- Up: `docker compose up -d`   ·   Down: `docker compose down`
- Health: Prometheus :9090 (Status → Targets) · Grafana :3000 · Alertmanager :9093
- Drift export (run after `config-audit report`, same cron job):
  `python3 scripts/export_config_drift.py <config-audit report dir> ./textfile_collector`

## Layout
- `docker-compose.yml` — the 5-service stack (prometheus, alertmanager, snmp_exporter,
  node_exporter, grafana)
- `prometheus/prometheus.yml` — scrape config (snmp_exporter relabel dance +
  node_exporter for the textfile collector)
- `prometheus/alert.rules.yml` — alert rules (InterfaceDown, ConfigDrift)
- `alertmanager/alertmanager.yml` — routing
- `grafana/provisioning/` + `grafana/dashboards/` — auto-provisioned datasource + dashboard
- `scripts/export_config_drift.py` — config-audit report JSON → Prometheus textfile format
- `textfile_collector/` — where the script writes; node_exporter reads `*.prom` files here

## Rules
- **Never commit secrets.** Grafana admin password comes from a gitignored `.env`
  (`GRAFANA_ADMIN_PASSWORD`); `.env.example` shows the shape. Never a literal password
  in `docker-compose.yml`.
- **Image tags are pinned to specific versions** (checked 2026-07-01: prometheus
  v3.13.0, alertmanager v0.33.0, snmp-exporter v0.30.1, node-exporter v1.11.1,
  grafana 13.0.3), not `:latest`. Re-verify and re-pin deliberately if you ever bump
  these — don't drift back to `:latest`.
- **`export_config_drift.py` writes atomically** (temp file + rename) — node_exporter's
  textfile collector can otherwise scrape a half-written `.prom` file mid-write. Keep
  this pattern if you touch the script.
- **`ConfigDrift` has no `for:` debounce, unlike `InterfaceDown`.** A drift finding is
  already a discrete, one-shot result from a completed `config-audit diff` run, not a
  noisy raw counter that flaps — there's nothing to debounce. Don't add a `for:` here
  by reflexive analogy to the interface alert; it would just delay a real finding.
- **CI (`.github/workflows/validate.yml`) brings the whole stack up on every push/PR**
  and checks all four services report healthy, plus that the `snmp-cisco` job is
  registered in Prometheus (it's expected to be `down`/`unknown` in CI — no real
  device reachable from a GitHub runner — this only proves the wiring, not live SNMP).
  Live-hardware validation (a real target going green) is still a manual, local step.
- The deliverable that matters is **one tuned alert** — the documented false-positive →
  fix (naive `ifOperStatus == 2` → add `and ifAdminStatus == 1` + `for: 2m`) — not a
  wall of dashboards. The tuning write-up IS the interview answer.
