# Verified backups and isolated recovery (Flow 6)

`infra/backup/recovery.py` creates a PostgreSQL/object-storage backup, verifies its integrity, and rehearses recovery into newly created destinations. The application is never started by the drill. Existing databases and buckets are never cleaned, overwritten or deleted by this tool.

This replaces the old timestamp-only destructive `restore.sh` interface. Legacy directories without a completion manifest cannot be verified or restored by this workflow. Preserve them under your existing recovery policy; create and validate a new bundle before replacing any earlier backup process.

## What a complete bundle proves

- PostgreSQL's custom-format dump, source table counts, schema version and known object references use **one exported repeatable-read snapshot**. Concurrent source changes cannot make the expected counts refer to a later state than the dump.
- The four configured current-object buckets are copied with opaque local filenames. S3 object keys never become filesystem paths. Each artifact has a size and SHA-256 checksum.
- PPE snapshots, corrective photos and completed report object references from that database snapshot must exist in the copy. Corrective evidence must also match its original database hash and size.
- Initial object inventory entries must remain unchanged through the copy. Newly arriving objects after the listing do not invalidate it; they are outside that copy. An overwritten/deleted inventoried object, missing reference, failed request or expired copy budget prevents completion.
- A completion manifest is published only after verification. Incomplete directories retain partial files and a pending manifest for investigation; they are not accepted as complete backups. The tool does not delete them or previous backups.

The database and object store are **not an atomic distributed snapshot**. Mutable branding URLs and remote resources are not reconciled. S3 version history, policies, lifecycle settings and encryption-key configuration are not exported. The manifest explicitly records exclusions: RabbitMQ pending messages, worker journals, Redis revocations and deployment secrets. Keep reviewed application/model artifacts, media mappings, configuration, bucket policies and secrets in their separately protected recovery systems.

A checksum is an integrity check, not an origin signature. Retain the emitted `manifest_sha256` in an independently controlled inventory or signed backup catalog. Restore requires that checksum. Only restore trusted artifacts: a PostgreSQL archive can contain executable database definitions.

## Runtime and credentials

Use the backend Python environment (`asyncpg`, `minio`, `urllib3` are already installed by `backend/requirements.txt`) and PostgreSQL clients compatible with the source server. For PostgreSQL 16, use PostgreSQL 16 `pg_dump` and `pg_restore`, or a reviewed compatible newer client/server pair. The backup identity needs read access to every application table and permission to export/read a transaction snapshot; the isolated restore identity needs permission to create databases and install the dumped schema.

Configure these values securely in the operator environment; the tool does not source `.env`, fall back to development passwords, print connection URLs or place passwords in subprocess arguments:

| Purpose | Environment variable |
| --- | --- |
| Source database | `BACKUP_DATABASE_URL` (`postgresql://…/database`, optional `?sslmode=require`/`verify-full`) |
| Source object storage | `BACKUP_S3_ENDPOINT` (`hostname:port`), `BACKUP_S3_ACCESS_KEY`, `BACKUP_S3_SECRET_KEY` |
| Optional source region | `BACKUP_S3_REGION` (default `us-east-1`) |
| Optional bucket names | `BACKUP_BUCKET_SNAPSHOTS`, `BACKUP_BUCKET_REPORTS`, `BACKUP_BUCKET_LOGOS`, `BACKUP_BUCKET_MODELS` |
| Isolated restore database server | `RESTORE_ADMIN_DATABASE_URL`, selecting its `postgres` maintenance database |
| Isolated restore storage | `RESTORE_S3_ENDPOINT`, `RESTORE_S3_ACCESS_KEY`, `RESTORE_S3_SECRET_KEY`, optional `RESTORE_S3_REGION` |

All four source buckets must exist, including empty ones. Backup storage credentials need list/get access; restore credentials need create-bucket, put/get and bucket-existence access on the isolated server. S3 HTTPS and certificate verification are enabled. `BACKUP_S3_LOCAL_HTTP=1` / `RESTORE_S3_LOCAL_HTTP=1` permit HTTP only on loopback for local fixtures, never on remote endpoints. PostgreSQL SSL follows the URL's `sslmode`; use the deployment's required TLS policy and native libpq trust configuration.

The optional `--pg-client-image postgres:16-alpine` adapter runs matching clients in Docker with Linux host networking. It is used by local/CI tests; it requires an already available, trusted image and Docker access. Prefer native clients for scheduled production backups. Pin a reviewed image digest if using the adapter outside tests. Container credentials are passed through its environment and are visible to privileged Docker operators. A timed-out client container is removed by its unique generated name.

## Create and verify

From the repository root, after configuring the environment:

```bash
./infra/backup/backup.sh --output backups/pilot-backup-001

backend/.venv/bin/python infra/backup/recovery.py verify \
  --bundle backups/pilot-backup-001 \
  --manifest-sha256 '<checksum retained from the create result>'
```

`BACKUP_PYTHON` can select a different prepared Python interpreter for the shell wrappers. Without `--output`, create uses `backups/<UTC timestamp>-<random suffix>`. An existing output directory is rejected. Directories/files are private to the operator; bundles contain sensitive camera URLs, account hashes, encrypted MFA seeds and incident evidence. Use an encrypted filesystem and approved encrypted offsite storage; the bundle itself is **not encrypted by this tool**.

The `verify` command reads only local files, checks every artifact and known reference, rejects extra files/symlinks/invalid paths, and returns `integrity_verified`. This alone is not a restore test. Backup supports at most 100,000 objects and 100,000 known references per bundle; it fails explicitly beyond those bounds. Plan a measured larger-scale or incremental backup solution before reaching the limit; no silent truncation occurs. There is no automatic retention deletion.

`--timeout` defaults to 1,800 seconds for each PostgreSQL client operation and each object-copy/read-back phase. Socket connection/read timeouts are finite; object deadlines are checked between streamed reads. This is not a guaranteed total end-to-end completion time. Database table counts and a long exported snapshot consume database resources; schedule and measure them on representative retention-sized data.

## Isolated restore drill

Prepare a separate PostgreSQL/object-storage environment and block its outbound access to workers, cameras and notification providers. Configure `RESTORE_*` settings for that environment, then run:

```bash
./infra/backup/restore.sh \
  --bundle backups/pilot-backup-001 \
  --manifest-sha256 '<independently retained checksum>' \
  --report backups/drill-reports/pilot-001.json
```

The report path must be new and outside the bundle. It is reserved before destination mutations. The tool:

1. Verifies the complete bundle and expected manifest hash before connecting to the target.
2. Creates a random `vg_restore_<uuid>` database from `template0` and revokes public CONNECT access. It never accepts an existing application database as the restore destination.
3. Uses `pg_restore --exit-on-error --single-transaction --no-owner --no-acl`. A failed restore is never reported as successful.
4. Reads the restored schema, every application table count and known object references, and compares them with the source snapshot manifest. Constraint/index/trigger creation errors fail the native restore.
5. Creates distinct `vg-restore-<run>-<role>` buckets, uploads every object and downloads it again to verify its original size/hash. Existing target buckets are rejected.
6. Writes `restore_verified` only after all checks pass. Failures retain a failed report and isolated targets for investigation; the operator owns cleanup. No application, report dispatcher, notification worker or AI worker is launched.

The JSON report includes destination names, schema/table/object/reference counts and elapsed drill time. `production_approved` remains false; `service_rto_seconds` and `rpo_seconds` remain null. File hashes, row counts and successful object read-back do not prove application usability, complete logical correctness, factory recovery timing or an agreed data-loss window. Run the isolated application acceptance checks in [FACTORY_PILOT_ACCEPTANCE.md](FACTORY_PILOT_ACCEPTANCE.md) separately, using the reported new bucket mapping.

## Scheduling, offsite copies and actual disaster recovery

Example systemd units are provided in `infra/backup/visionguard-backup.service` and `.timer`; they are not installed or enabled by this change. Adjust paths, operator permissions, cadence and time budgets against the company's approved RPO. The illustrative daily timer is not an accepted recovery target. Have operations monitor command failures, missed schedules, disk space, incomplete bundles and the age of the last verified **offsite** copy.

After successful creation, transfer the complete directory with approved encrypted offsite tooling, retain the independent manifest hash and verify the retrieved copy before a drill. Do not remove the previous known-good copy merely because a new command exited successfully. Decide encryption-key custody, retention, legal holds, provider permissions, offsite credentials and restore ownership with the company; no schedule, upload, deletion or provider write has been activated here.

Before a real cutover:

- Establish one authoritative coordinator and isolate the old deployment. Reconcile RabbitMQ messages, worker journals, receipts and pending outboxes; a database backup alone cannot reconstruct acknowledged events lost outside that snapshot. Preserve worker state volumes and follow [DURABLE_EDGE_EVENTS.md](DURABLE_EDGE_EVENTS.md) and [WORKER_FAILOVER.md](WORKER_FAILOVER.md).
- Recover the correct deployment secrets through the protected secret store. Flow 5's TOTP secrets depend on the original `JWT_SECRET`; changing it without an MFA recovery plan makes them unreadable. Restored authentication state can predate logout/revocation: invalidate all restored sessions by changing user `auth_version` values with an attributed audit transaction before enabling access. See [ACCOUNT_SECURITY.md](ACCOUNT_SECURITY.md).
- Reapply reviewed non-owner application roles, storage policies, TLS, media mappings and bucket names. Inspect queued reports/notifications before starting dispatchers to account for duplicates or older work. Do not reuse historical detection-health records as proof that cameras are monitoring now.
- Measure actual service recovery and lost-data boundaries against the frozen company RTO/RPO, test authorized evidence/report access, and obtain the site recovery decision before reconnecting factory traffic.

## Local validation limits

The automated drill uses a newly migrated PostgreSQL database, populated incident/report/photo/audit rows, real `pg_dump`/`pg_restore` clients and the real MinIO SDK against a local S3 HTTP protocol fixture. It changes the source after snapshot export to verify that the restored name/table set remains at the original snapshot, reconciles objects, and confirms the restored append-only audit trigger rejects deletion. Corruption, incomplete backups, missing references, source object changes, private paths, target reuse, native failures/timeouts and read-back failure have regression coverage.

The S3 fixture does not establish real provider authentication, bucket policies, TLS, multipart throughput or durability. Offsite encryption/retrieval, retention-sized capacity, broker/edge recovery, managed PostgreSQL permissions and full application/site restore remain deployment acceptance gates. No production data was restored or overwritten in the cloud task.
