# Fleet monitoring and control-plane measurements

P6 replaces the two-worker static scrape list with file discovery, adds a registry-to-Prometheus coverage gate, verifies constant SELECT count for full lease renewal at 1 and 200 cameras, and provides a synthetic API/broker/database workload. It does not discover camera-per-GPU capacity or certify the 1,000-camera deployment.

## Register every worker in monitoring

Copy `infra/monitoring/fleet.example.json` into ignored `capacity-data/fleet.json`. Replace the placeholders with real enterprise/factory UUIDs and include every nondeleted registered worker, including standby workers. Each business worker ID and metrics host:port must be unique. Configure workers for their factory before passing this gate. The inventory is operator-controlled: never derive scrape URLs from worker-supplied hostnames.

For each enterprise, `token_env` names an environment variable containing a short-lived enterprise/system administrator JWT. It contains the **variable name only**, never the token. Worker entries contain `worker_id`, `enterprise_id`, `factory_id`, `target` (host:port) and optional `scheme` (`http` or `https`). Metrics endpoints must be reachable from Prometheus over trusted private networks. HTTPS uses normal certificate validation; certificates/private-network reachability need deployment testing. Protect metrics and the Prometheus API from public access.

Using the backend Python environment (which includes httpx), from repository root:

```sh
backend/.venv/bin/python infra/monitoring/fleet.py generate \
  --inventory capacity-data/fleet.json --output capacity-data/prometheus-targets/workers.json
```

Set `FLEET_TARGETS_DIR` to that directory's absolute host path in production environment settings. Ensure this dedicated target directory is readable/traversable by the Prometheus container user (for example mode 0755); do not loosen permissions on credential or evidence directories. The production overlay requires it and mounts the **directory** read-only; atomic file replacement remains visible to Prometheus. The default committed `infra/prometheus/targets/workers.json` is only a two-worker development list and lacks production tenant/factory labels. It cannot pass production coverage. Do not commit site addresses, inventory files, JWTs or generated reports.

Start/recreate Prometheus to adopt the file-discovery configuration once. Later file changes are discovered without restarting Prometheus (15-second refresh plus scrape interval). Validate the complete file before replacing it. The generator rejects empty inventory, malformed IDs/endpoints and duplicates, and writes atomically. Retain the previous valid file for rollback; do not delete targets to silence a failed worker.

Run the coverage gate after provisioning workers, after every inventory/deployment change and on a scheduled interval (for example every five minutes):

```sh
# Populate the named JWT environment variables securely before this command.
backend/.venv/bin/python infra/monitoring/fleet.py audit \
  --inventory capacity-data/fleet.json \
  --backend-url https://authorized-staging.example \
  --prometheus-url http://private-prometheus:9090 \
  --output capacity-results/fleet-coverage.json
```

Exit 0 means the snapshot matches; exit 1 is a coverage mismatch; exit 2 means inputs/authentication/network/response validation failed. A failed audit writes a failure/error report instead of leaving an old success report. Fail your deployment gate and connect scheduled nonzero exits to the existing operations scheduler/notification system. Scheduling and external notification delivery are deployment responsibilities, not started by this command.

The audit compares each tenant's authenticated `/api/v1/workers` registry against the complete inventory, active Prometheus targets, expected endpoint/factory labels, recent healthy scrapes and `vg_worker_identity_info`. Workers export `reported_worker_id` and `reported_enterprise_id` independently of scrape labels, so pointing two labeled targets at the same worker cannot fake coverage. Registered workers absent from inventory, down/missing/duplicate targets, mismatched scope and missing runtime identity all fail. It checks the tenants listed in the inventory; maintain an authoritative enterprise list too. A successful coverage audit proves observability at that moment, not model readiness, detection accuracy or camera capacity.

Existing per-worker/frame/lease/backlog alert rules continue to apply. Host/GPU resource exporters, durable broker metrics, PostgreSQL server metrics, Alertmanager destinations and cross-factory private connectivity still need site configuration. The benchmark samples queue/pool activity only during its run; it is not a production exporter.

## Measure API, broker and database together

The Linux backend tool `backend/scripts/measure_fleet.py` only accepts an **empty, migrated database ending `_capacity_test`** and rejects production mode. Create a dedicated database with test credentials, migrate it to head, and set `CAPACITY_DATABASE_URL` securely. The script also uses the configured `RABBITMQ_URL` and `REDIS_URL`; use isolated staging services/vhosts. It refuses a database containing any enterprise. It does not reset, truncate or delete an existing dataset, so each repetition needs a new test database.

From `backend/`:

```sh
# First migrate the dedicated database using DATABASE_URL in environment settings.
.venv/bin/alembic upgrade head
.venv/bin/python scripts/measure_fleet.py \
  --factories 5 --cameras-per-factory 200 --workers-per-factory 4 \
  --history-events 1000 --seconds 60 --events-per-second 10 --reads-per-second 6 \
  --p95-ms 750 --event-p95-ms 2000 \
  --output ../capacity-results/control-plane-1000.json
```

This seeds 1,000 camera records across five factories and 20 simulated worker identities. Each worker has 50 camera assignments. These are metadata records: no streams or models start. Real loopback HTTP exercises authentication, heartbeat, lease/configuration polls and populated camera/violation/alert list endpoints. Concurrent worker polls occur every 30 seconds, including a synchronized renewal burst. Real RabbitMQ publisher confirmations feed the actual fenced consumer and PostgreSQL receipt/violation/alert/outbox transactions through a unique private exchange/queue. The backend lifespan and notification delivery worker are deliberately not started. No email, Slack, webhook, evidence upload or camera recording occurs.

The warmup writes the requested history through the same consumer before measuring reads, distributed over `--history-cameras` (default 100, capped to the fleet size). The timed phase covers the whole fleet, so previously unseen cameras exercise new alert/outbox writes as well as cooldown deduplication. Reports count timed new alerts separately. The timed workload uses scheduled event/read rates with bounded read concurrency; skipped schedules fail. Reports include per-route latency percentiles, offered/persisted counts, publish-to-handler-completion latency, sampled ready-queue backlog, consumer concurrency, SQL statement count and connection-pool peak usage. Read and event latency gates, missing persisted events, API errors and consumer redelivery fail the run. The report records revision/source hash, package versions, runtime limits and explicit exclusions. It returns a failing exit status on unmet gates/errors. Preserve every report, including failures. A short pass establishes only the tested synthetic level and rates.

The queue is unique and auto-deleted/cleaned up, and the generated tenant data remains in the dedicated test database for inspection. Do not run a production backend against that test database: it contains pending synthetic outbox jobs. Dispose of the dedicated database after retaining the report according to your test-environment policy. Broker restart durability, outbox delivery, evidence latency, resource saturation, representative retention-sized data and WAN/TLS behavior are separate measurements. API and load generator share a process here, so use the external k6 test for independent client load on the deployment.

## External read-load gate

For an authorized populated staging deployment, set `CAPACITY_BASE_URL`, `CAPACITY_ACCESS_TOKEN`, `CAPACITY_EXPECTED_CAMERAS`, and optionally `CAPACITY_MIN_HISTORY` (default 100 persisted alerts and violations). Run:

```sh
CAPACITY_READ_CYCLES_PER_SECOND=2 CAPACITY_DURATION=10m k6 run \
  --summary-export capacity-results/api-staging.json infra/capacity/api-load.js
```

Each cycle issues three parallel reads (alerts, violations and cameras). Constant arrival rate and a zero dropped-iteration gate prevent slower responses silently reducing offered load. Every endpoint must meet p95 < 750 ms, every read must succeed, and the expected camera/history population must be present. Adjust targets from an agreed pilot SLO before running, not after seeing a failure. No mutations are sent. Real network/TLS, production-like history, multiple tenant scopes and concurrent writes still need representative staging measurements.

## Acceptance boundary

Use these tools before the 10–20 → 50–100 → 200 real-camera rollout per factory. Retain site coverage reports, measured workload parameters and failure-drill results. P4 target-GPU validation, P5 site recovery/RTO and P7 accuracy/soak/shared-service recovery remain open. Neither a 1,000-record database nor a synthetic 1,000-camera metadata run means this hardware can process 1,000 video streams.

## Local evidence

A five-factory, 1,000-camera-record burst (20 synthetic events/second for 60 seconds, six reviewer reads/second, 20 synchronized polling workers) exposed assignment latency above the 750 ms test gate. Removing a redundant admission pass and excluding other live owners from lease-row locking reduced measured assignment p95 from 1,193 ms to 644 ms under the same gates. All 1,200 timed events persisted and 900 new timed alerts were created. The API process still reached its 30-connection pool ceiling; do not assume spare capacity. See the [retained before/after reports](evidence/P6_CONTROL_PLANE_2026-10-16.json) and [remediation roadmap](MULTI_FACTORY_REMEDIATION.md) for scope, versions and remaining site gates.
