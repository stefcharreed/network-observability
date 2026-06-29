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
- Pin image `:latest` tags to specific versions before relying on the stack.
- The deliverable that matters is **one tuned alert** — the documented false-positive →
  fix (naive `ifOperStatus == 2` → add `and ifAdminStatus == 1` + `for: 2m`) — not a
  wall of dashboards. The tuning write-up IS the interview answer.
