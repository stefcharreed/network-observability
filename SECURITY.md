# Security

If you find a vulnerability in this stack's configuration (e.g. a way to reach an
unauthenticated service from beyond the docker host, or a secret that made it into the
repo), please report it privately via [GitHub's private vulnerability reporting](../../security/advisories/new)
rather than a public issue. You'll get a response within a week.

Notes on scope:

- This repo contains configuration only — no credentials, community strings, or real
  device addresses. Secrets are supplied at runtime via a gitignored `.env` and
  file-based secrets under `alertmanager/secrets/` (also gitignored).
- By design, Grafana is the only service exposed beyond the docker host; Prometheus,
  Alertmanager, and the exporters bind to `127.0.0.1` because they have no
  authentication of their own. A configuration change that silently widens that
  exposure is a valid finding.
