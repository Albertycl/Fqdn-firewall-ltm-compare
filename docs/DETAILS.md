# FQDN Search in multiple FW and LTM comparing: full details

[Back to the short README](../README.md)

**Live demo:** https://fqdn-seachtool.albertycliu.xyz (made-up demo data, no login)

Web portal for analysing network configurations. Search an IP address, an FQDN or an
object name and see the load-balancer virtual servers, pools and nodes that reference
it, together with the firewall address objects, groups, policies and NAT rules that
match, including smart subnet matching (a `/32` found inside a `/24` policy).

Everything shown comes from parsed device configs. This public copy ships **made-up demo
data only** (documentation-range IPs, `demo-*.example` domains).

## What it is and why it matters for SRE

During an incident the question is usually "what sits behind this IP, and which firewall
rule lets traffic reach it?". Answering it by hand means grepping F5 and FortiGate configs
from several sites. This tool parses them once a day and makes them searchable in one place.

Skills this repo shows:

- **Containers**: one Dockerfile per component, a compose file, a bundled-or-external database switch.
- **GitOps and CI/CD**: GitHub Actions builds the images, a separate GitOps repo holds the manifests, Argo CD deploys to K3s.
- **Config hygiene**: no default password, every address comes from the environment, secrets are never in Git.
- **Operations**: a daily update job with a run-history page, and a rollback path with `git revert`.

Deliberately simple: no authentication (it is an internal-style demo), one replica, a single database.

## Architecture

| Component | Tech | Notes |
|---|---|---|
| Frontend | Quasar (Vue 3), served by nginx, port 5434 | nginx proxies `/api/` to the backend, so no address is baked into the bundle |
| Backend | Flask blueprints + SQLAlchemy under gunicorn, port 5432 | parsers for F5 LTM and FortiGate configs, search, daily update |
| Database | MariaDB | databases `fqdn_tool` (parsed configs) and `fqdn_v3` (FQDN lookup tables) |
| Daily update | `cron` container (optional) | calls `/api/download/daily` at 06:00; off by default |

Request flow: browser, nginx (`/api/`), Flask search blueprint, MariaDB, JSON back to the UI.

GitOps manifests: [`Albertycl/Gitops-apps`](https://github.com/Albertycl/Gitops-apps), folder `manifests/fqdn-compare/`.

```
backend/      Flask app (blueprint/, parsers/, services/, scripts/)
frontend/     Quasar SPA and nginx image
docker/cron/  optional daily-update container
demo/         made-up seed data and the database bootstrap
```

## Install and run

### Locally with Docker Compose

Prerequisites: Docker with the Compose plugin.

```bash
cp .env.example .env            # then set DB_PASSWORD (letters and digits; no spaces or $)
docker compose --profile bundled-db up -d --build
./demo/load-demo-data.sh        # loads the made-up demo rows
```

Open `http://<host>:5434`. The search box opens with `sb-results.demo-corp.example`.

Stop with `docker compose --profile bundled-db down` (add `-v` to delete the data).

Main variables (all in `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DB_PASSWORD` | none, required | Database password; compose refuses to start without it |
| `DB_HOST` / `DB_PORT` | `db` / `3306` | Point at a database you already run (leave the `bundled-db` profile off) |
| `FQDN_DB_ENABLED` | `true` | Turn the FQDN lookup on or off |
| `CONFIG_SOURCE_URL` | `http://config-server.example/configs/` | Where the daily update downloads configs from; only used with the `daily-update` profile |

The daily update is off by default because it needs a reachable config server and
replaces the demo data. Enable it with `docker compose --profile daily-update up -d`.

### On Kubernetes (K3s) with Argo CD

1. One-time bootstrap of the app-of-apps root: `kubectl apply -f argocd/root-app.yaml` (in `Gitops-apps`, done once for the cluster). Argo CD then creates the namespace and the workloads.
2. Create the Secret by hand (never in Git): `fqdn-db` with key `db-password`.
3. After the first CI run set the GHCR packages `fqdn-compare-backend` and `fqdn-compare-frontend` to public (the pods use no pull secret).
4. Load the demo data once (the backend creates the tables on start-up):
   ```bash
   N=fqdn-compare
   kubectl exec -i -n $N mariadb-0 -- sh -c 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb -uroot fqdn_v3'  < demo/seed_fqdn_demo.sql
   kubectl exec -i -n $N mariadb-0 -- sh -c 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb -uroot fqdn_tool' < demo/seed_firewall_demo.sql
   ```
5. Check: `kubectl get applications -n argocd` shows `Synced` and `Healthy`, and `kubectl get pods -n fqdn-compare` shows all pods `Running`.

## CI/CD and rollback

1. A push to `main` runs `.github/workflows/ci.yml`: build the backend and frontend images.
2. Images are pushed to GHCR, tagged with the commit SHA and `latest`.
3. The `update-gitops` job runs `kustomize edit set image` in `gitops-apps/manifests/fqdn-compare/` and pushes a "deploy <sha>" commit with a deploy key.
4. Argo CD sees the commit and syncs (automated, prune, self-heal).

Roll back by running `git revert` on the "deploy <sha>" commit in `Gitops-apps`.
`kubectl rollout undo` does not stick, because self-heal restores the Git state.

## Monitoring

The pods have no metrics endpoint. Cluster-level monitoring (Prometheus and Alertmanager) comes from the shared cluster stack. The app records every daily-update run and shows it on the **/update-history** page and at `GET /api/download/history`.

## Known limits

- No authentication: there is no login page and the API is open. Do not expose it with real data.
- Several routes change data through plain GET or POST calls (for example `/api/download/daily`).
- Single replica, one database, no backups of the demo data (it can be reloaded from `demo/`).
- Images run as root and have no health checks; the base images are old (Python 3.8).
