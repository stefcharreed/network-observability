# CLAUDE.md — network-observability

Pillar 4 of the NetDevOps platform: Prometheus + Alertmanager + snmp_exporter + Grafana,
as code. **Standalone** — no dependency on the config-audit code.

## Commands
- Up: `docker compose up -d`   ·   Down: `docker compose down`
- Health: Prometheus :9090 (Status → Targets) · Grafana :3000 · Alertmanager :9093

## Layout
- `docker-compose.yml` — the 4-service stack
- `prometheus/prometheus.yml` — scrape config (snmp_exporter relabel dance)
- `prometheus/alert.rules.yml` — alert rules (InterfaceDown)
- `alertmanager/alertmanager.yml` — routing
- `grafana/provisioning/` + `grafana/dashboards/` — auto-provisioned datasource + dashboard

## Rules
- **Never commit secrets.** Grafana admin password comes from a gitignored `.env`
  (`GRAFANA_ADMIN_PASSWORD`); `.env.example` shows the shape. Never a literal password
  in `docker-compose.yml`.
- **Image tags are pinned to specific versions** (checked 2026-07-01: prometheus
  v3.13.0, alertmanager v0.33.0, snmp-exporter v0.30.1, grafana 13.0.3), not `:latest`.
  Re-verify and re-pin deliberately if you ever bump these — don't drift back to
  `:latest`.
- **CI (`.github/workflows/validate.yml`) brings the whole stack up on every push/PR**
  and checks all four services report healthy, plus that the `snmp-cisco` job is
  registered in Prometheus (it's expected to be `down`/`unknown` in CI — no real
  device reachable from a GitHub runner — this only proves the wiring, not live SNMP).
  Live-hardware validation (a real target going green) is still a manual, local step.
- The deliverable that matters is **one tuned alert** — the documented false-positive →
  fix (naive `ifOperStatus == 2` → add `and ifAdminStatus == 1` + `for: 2m`) — not a
  wall of dashboards. The tuning write-up IS the interview answer.
