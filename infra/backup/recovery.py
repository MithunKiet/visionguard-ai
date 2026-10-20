"""Verified logical backups and restore drills into newly created destinations.

Run with the backend Python environment. Credentials are read only from environment
variables, never command arguments, manifests or diagnostic output.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
from minio import Minio
import urllib3

FORMAT = 1
MAX_ENTRIES = 100_000
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
CHUNK = 1024 * 1024
BUCKET_ROLES = ("snapshots", "reports", "logos", "models")
EXCLUSIONS = [
    "rabbitmq_pending_messages",
    "worker_journals",
    "redis_revocations",
    "deployment_secrets",
    "external_branding_urls",
    "s3_versions_policies_and_lifecycle",
]


class RecoveryError(Exception):
    """A sanitized operator-facing error."""


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest_file(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return {"sha256": digest.hexdigest(), "size": size}


def private_write(path, content):
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
    ) as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json(path, value):
    private_write(
        path,
        (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode(),
    )


def read_manifest(root, expected_hash=None, manifest_name="manifest.json"):
    path = root / manifest_name
    if (
        root.is_symlink()
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_MANIFEST_BYTES
    ):
        raise RecoveryError("Missing, oversized or unsafe completion manifest")
    if expected_hash is not None and digest_file(path)["sha256"] != expected_hash:
        raise RecoveryError(
            "Manifest does not match the independently retained checksum"
        )

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RecoveryError("Duplicate manifest field")
            result[key] = value
        return result

    try:
        result = json.loads(
            path.read_text(),
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                RecoveryError("Nonfinite manifest value")
            ),
        )
    except (ValueError, UnicodeError):
        raise RecoveryError("Invalid manifest JSON") from None
    if (
        not isinstance(result, dict)
        or type(result.get("format")) is not int
        or result.get("format") != FORMAT
        or result.get("status") != "complete"
    ):
        raise RecoveryError("Unsupported or incomplete backup")
    return result


def verify_bundle(root, expected_hash=None, *, manifest_name="manifest.json"):
    root = Path(root).absolute()
    manifest = read_manifest(root, expected_hash, manifest_name)
    objects = manifest.get("objects")
    refs = manifest.get("references")
    tables = manifest.get("table_counts")
    if (
        not isinstance(objects, list)
        or not isinstance(refs, list)
        or max(len(objects), len(refs)) > MAX_ENTRIES
    ):
        raise RecoveryError("Invalid or oversized object inventory")
    if (
        not isinstance(tables, dict)
        or not tables
        or len(tables) > 1000
        or any(
            not isinstance(name, str) or type(count) is not int or count < 0
            for name, count in tables.items()
        )
    ):
        raise RecoveryError("Invalid table counts")
    buckets = manifest.get("buckets")
    if (
        not isinstance(buckets, dict)
        or set(buckets) != set(BUCKET_ROLES)
        or len(set(buckets.values())) != 4
    ):
        raise RecoveryError("Invalid bucket mapping")
    allowed_buckets = set(buckets.values())
    entries = [manifest.get("database"), *objects]
    files = {manifest_name}
    identities = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise RecoveryError("Invalid artifact entry")
        relative = entry.get("path", "")
        expected_path = (
            "postgres.dump" if index == 0 else f"objects/{index - 1:08d}.bin"
        )
        if relative != expected_path or relative in files:
            raise RecoveryError("Invalid or duplicate artifact path")
        if (
            not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("sha256", "")))
            or type(entry.get("size")) is not int
            or entry["size"] < 0
        ):
            raise RecoveryError("Invalid artifact checksum or size")
        artifact = root / relative
        if (
            artifact.is_symlink()
            or artifact.parent.is_symlink()
            or not artifact.is_file()
        ):
            raise RecoveryError("Missing or unsafe backup artifact")
        if digest_file(artifact) != {key: entry[key] for key in ("sha256", "size")}:
            raise RecoveryError("Backup artifact checksum mismatch")
        files.add(relative)
        if index:
            identity = (entry.get("bucket"), entry.get("key"))
            if (
                identity[0] not in allowed_buckets
                or not isinstance(identity[1], str)
                or not identity[1]
                or identity in identities
            ):
                raise RecoveryError("Invalid or duplicate object identity")
            identities[identity] = entry
    for directory, dirs, filenames in os.walk(root, followlinks=False):
        for name in [*dirs, *filenames]:
            path = Path(directory) / name
            if path.is_symlink() or (
                path.is_file() and path.relative_to(root).as_posix() not in files
            ):
                raise RecoveryError("Unexpected file or symlink in backup")
    for ref in refs:
        if not isinstance(ref, dict):
            raise RecoveryError("Invalid database object reference")
        entry = identities.get((ref.get("bucket"), ref.get("key")))
        if not entry:
            raise RecoveryError("A database-referenced object is absent from backup")
        if ref.get("sha256") and ref["sha256"] != entry["sha256"]:
            raise RecoveryError("Evidence checksum differs from its database record")
        if ref.get("size") is not None and ref["size"] != entry["size"]:
            raise RecoveryError("Evidence size differs from its database record")
    return manifest


def database_url(variable):
    value = os.environ.get(variable, "").replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )
    parts = urlsplit(value)
    if (
        parts.scheme not in {"postgres", "postgresql"}
        or not parts.hostname
        or not parts.username
        or not parts.path.strip("/")
    ):
        raise RecoveryError(f"Configure {variable} in the environment")
    query = parse_qs(parts.query)
    if set(query) - {"sslmode"}:
        raise RecoveryError("Only sslmode is supported in database URL query options")
    return value


def pg_env(url):
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    env = os.environ.copy()
    # Do not accidentally inherit a different target from a libpq service definition.
    for key in ("PGSERVICE", "PGSERVICEFILE", "PGOPTIONS"):
        env.pop(key, None)
    env.update(
        PGHOST=parts.hostname,
        PGPORT=str(parts.port or 5432),
        PGUSER=unquote(parts.username),
        PGPASSWORD=unquote(parts.password or ""),
        PGDATABASE=unquote(parts.path[1:]),
        PGSSLMODE=query.get("sslmode", ["prefer"])[0],
        PGCONNECT_TIMEOUT="10",
    )
    return env


def pg_command(tool, args, image=None, container_name=None):
    if image:
        # Optional Linux test adapter: existing PG image supplies matching clients.
        return [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "-i",
            "--network",
            "host",
            *[
                item
                for key in (
                    "PGHOST",
                    "PGPORT",
                    "PGUSER",
                    "PGPASSWORD",
                    "PGDATABASE",
                    "PGSSLMODE",
                    "PGCONNECT_TIMEOUT",
                )
                for item in ("-e", key)
            ],
            image,
            tool,
            *args,
        ]
    return [tool, *args]


def run_pg(
    tool, args, url, *, image=None, input_path=None, output_path=None, timeout=1800
):
    container_name = "vg-recovery-client-" + uuid4().hex if image else None
    with tempfile.TemporaryFile() as errors:
        source = input_path.open("rb") if input_path else subprocess.DEVNULL
        target = (
            os.fdopen(
                os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
            )
            if output_path
            else subprocess.DEVNULL
        )
        try:
            result = subprocess.run(
                pg_command(tool, args, image, container_name),
                env=pg_env(url),
                stdin=source,
                stdout=target,
                stderr=errors,
                timeout=timeout,
                check=False,
            )
            if result.returncode:
                raise RecoveryError(f"{tool} failed; backup/restore is incomplete")
        except subprocess.TimeoutExpired:
            if container_name:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    check=False,
                )
            raise RecoveryError(f"{tool} exceeded its time budget") from None
        finally:
            if input_path:
                source.close()
            if output_path:
                target.close()


def s3_client(prefix):
    endpoint = os.environ.get(prefix + "_S3_ENDPOINT")
    access = os.environ.get(prefix + "_S3_ACCESS_KEY")
    secret = os.environ.get(prefix + "_S3_SECRET_KEY")
    if not all((endpoint, access, secret)):
        raise RecoveryError(
            f"Configure {prefix}_S3_ENDPOINT, {prefix}_S3_ACCESS_KEY and {prefix}_S3_SECRET_KEY"
        )
    insecure = os.environ.get(prefix + "_S3_LOCAL_HTTP") == "1"
    if insecure and urlsplit("http://" + endpoint).hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise RecoveryError("Plain HTTP is restricted to loopback storage fixtures")
    return Minio(
        endpoint,
        access_key=access,
        secret_key=secret,
        secure=not insecure,
        region=os.environ.get(prefix + "_S3_REGION", "us-east-1"),
        http_client=urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=5, read=30), retries=False
        ),
    )


def inventory(client, buckets, deadline=None):
    result = {}
    for bucket in buckets.values():
        for item in client.list_objects(bucket, recursive=True):
            if deadline is not None and time.monotonic() >= deadline:
                raise RecoveryError("Object copy exceeded its time budget")
            if len(result) >= MAX_ENTRIES:
                raise RecoveryError(
                    "Object inventory exceeds the supported backup bound"
                )
            result[(bucket, item.object_name)] = (item.etag, item.size)
    return result


def copy_objects(client, buckets, root, timeout=1800):
    deadline = time.monotonic() + timeout
    before = inventory(client, buckets, deadline)
    (root / "objects").mkdir(mode=0o700)
    entries = []
    for index, ((bucket, key), (etag, size)) in enumerate(sorted(before.items())):
        relative = f"objects/{index:08d}.bin"
        response = client.get_object(bucket, key)
        try:
            if response.headers.get("ETag", "").strip('"') != etag:
                raise RecoveryError("Object changed during backup")
            with os.fdopen(
                os.open(root / relative, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                "wb",
            ) as output:
                written = 0
                for chunk in response.stream(CHUNK):
                    written += len(chunk)
                    if written > size or time.monotonic() >= deadline:
                        raise RecoveryError(
                            "Object exceeded expected size or copy time budget"
                        )
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            entry = {
                "path": relative,
                "bucket": bucket,
                "key": key,
                "content_type": response.headers.get(
                    "Content-Type", "application/octet-stream"
                ),
                **digest_file(root / relative),
            }
            if entry["size"] != size:
                raise RecoveryError("Object was truncated or changed during backup")
            entries.append(entry)
        finally:
            response.close()
            response.release_conn()
    after = inventory(client, buckets, deadline)
    # New arrivals after the listing do not belong to this copy and are harmless.
    # The earlier PostgreSQL snapshot cannot reference those later arrivals.
    if any(after.get(identity) != metadata for identity, metadata in before.items()):
        raise RecoveryError(
            "An inventoried object changed or disappeared during backup"
        )
    return entries


async def table_counts(connection):
    rows = await connection.fetch("""SELECT schemaname, tablename FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema') AND schemaname NOT LIKE 'pg_toast%'
        ORDER BY schemaname, tablename""")
    result = {}
    for row in rows:
        schema, table = row["schemaname"], row["tablename"]
        quoted = (
            '"' + schema.replace('"', '""') + '"."' + table.replace('"', '""') + '"'
        )
        result[schema + "." + table] = await connection.fetchval(
            "SELECT count(*) FROM " + quoted
        )
    return result


async def references(connection, buckets):
    result = []
    queries = [
        (
            buckets["snapshots"],
            "SELECT DISTINCT snapshot_key AS key, NULL::text AS sha256, NULL::bigint AS size FROM ppe.violations WHERE snapshot_key IS NOT NULL AND snapshot_key <> ''",
        ),
        (
            buckets["snapshots"],
            "SELECT object_key AS key, sha256, size_bytes AS size FROM alerts.corrective_evidence",
        ),
        (
            buckets["reports"],
            "SELECT DISTINCT object_key AS key, NULL::text AS sha256, NULL::bigint AS size FROM reports.reports WHERE status = 'Completed' AND object_key IS NOT NULL",
        ),
    ]
    for bucket, query in queries:
        async for row in connection.cursor(query):
            if len(result) >= MAX_ENTRIES:
                raise RecoveryError(
                    "Database object references exceed the supported backup bound"
                )
            result.append({"bucket": bucket, **dict(row)})
    return result


async def create_backup(root, url, client, buckets, image=None, timeout=1800):
    root = Path(root).absolute()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    started = utc()
    connection = await asyncpg.connect(url, timeout=10, command_timeout=timeout)
    try:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            snapshot = await connection.fetchval("SELECT pg_export_snapshot()")
            schema = await connection.fetchval(
                "SELECT version_num FROM public.alembic_version"
            )
            counts = await table_counts(connection)
            refs = await references(connection, buckets)
            await asyncio.to_thread(
                run_pg,
                "pg_dump",
                [
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--snapshot=" + snapshot,
                    "--lock-wait-timeout=10000",
                ],
                url,
                image=image,
                output_path=root / "postgres.dump",
                timeout=timeout,
            )
        # The dump and expected counts/references share one exported PostgreSQL snapshot.
        objects = await asyncio.to_thread(copy_objects, client, buckets, root, timeout)
        manifest = {
            "format": FORMAT,
            "status": "complete",
            "started_at": started,
            "completed_at": utc(),
            "schema_version": schema,
            "table_counts": counts,
            "buckets": buckets,
            "database": {
                "path": "postgres.dump",
                **digest_file(root / "postgres.dump"),
            },
            "objects": objects,
            "references": refs,
            "excluded": EXCLUSIONS,
            "cross_store_atomic": False,
            "production_approved": False,
        }
        # Flush the dump before publishing any completion marker.
        with (root / "postgres.dump").open("rb") as dump:
            os.fsync(dump.fileno())
        # Publish completion only after every file and database reference validates.
        write_json(root / "manifest.pending.json", manifest)
        verify_bundle(root, manifest_name="manifest.pending.json")
        sync_directory(root / "objects")
        (root / "manifest.pending.json").rename(root / "manifest.json")
        sync_directory(root)
        sync_directory(root.parent)
        return {
            "status": "backup_complete",
            "bundle": str(root),
            "manifest_sha256": digest_file(root / "manifest.json")["sha256"],
            "objects": len(objects),
            "tables": len(counts),
            "production_approved": False,
        }
    finally:
        await connection.close()


def restore_objects(client, root, manifest, mapping, timeout=1800):
    deadline = time.monotonic() + timeout
    for target in mapping.values():
        if client.bucket_exists(target):
            raise RecoveryError("Restore bucket already exists; refusing to reuse it")
        client.make_bucket(target)
    for entry in manifest["objects"]:
        if time.monotonic() >= deadline:
            raise RecoveryError("Object restore exceeded its time budget")
        target = mapping[entry["bucket"]]
        with (root / entry["path"]).open("rb") as source:
            client.put_object(
                target,
                entry["key"],
                source,
                entry["size"],
                content_type=entry["content_type"],
            )
        response = client.get_object(target, entry["key"])
        try:
            digest = hashlib.sha256()
            size = 0
            for chunk in response.stream(CHUNK):
                digest.update(chunk)
                size += len(chunk)
                if size > entry["size"] or time.monotonic() >= deadline:
                    raise RecoveryError(
                        "Object read-back exceeded expected size or time budget"
                    )
            if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                raise RecoveryError("Restored object failed read-back verification")
        finally:
            response.close()
            response.release_conn()
    return mapping


async def restore_drill(
    root, expected_hash, admin_url, client, report, image=None, timeout=1800
):
    root, report = Path(root).absolute(), Path(report).absolute()
    if report.exists() or report.resolve().is_relative_to(root.resolve()):
        raise RecoveryError("Choose a new report path outside the backup bundle")
    if not re.fullmatch(r"[a-f0-9]{64}", expected_hash or ""):
        raise RecoveryError("An independently retained manifest checksum is required")
    manifest = verify_bundle(root, expected_hash)
    if unquote(urlsplit(admin_url).path) != "/postgres":
        raise RecoveryError(
            "RESTORE_ADMIN_DATABASE_URL must select the postgres maintenance database"
        )
    drill_id = uuid4().hex
    target = "vg_restore_" + drill_id
    parts = urlsplit(admin_url)
    target_url = urlunsplit((parts.scheme, parts.netloc, "/" + target, parts.query, ""))
    result = {
        "status": "failed",
        "started_at": utc(),
        "database": target,
        "database_created": False,
        "bucket_mapping": {},
        "manifest_sha256": expected_hash,
        "production_approved": False,
        "services_started": False,
        "rpo_seconds": None,
        "service_rto_seconds": None,
    }
    start = time.monotonic()
    report.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the report before any destination mutation; concurrent runs cannot reuse it.
    write_json(report, {**result, "status": "running"})
    admin = None
    try:
        admin = await asyncpg.connect(admin_url, timeout=10, command_timeout=timeout)
        # Never --clean, never restore into an existing database, never start the application.
        await admin.execute(f'CREATE DATABASE "{target}" TEMPLATE template0')
        result["database_created"] = True
        await admin.execute(f'REVOKE CONNECT ON DATABASE "{target}" FROM PUBLIC')
        await asyncio.to_thread(
            run_pg,
            "pg_restore",
            [
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-acl",
                "--dbname=" + target,
            ],
            target_url,
            image=image,
            input_path=root / "postgres.dump",
            timeout=timeout,
        )
        restored = await asyncpg.connect(
            target_url, timeout=10, command_timeout=timeout
        )
        try:
            async with restored.transaction(isolation="repeatable_read", readonly=True):
                counts = await table_counts(restored)
                schema = await restored.fetchval(
                    "SELECT version_num FROM public.alembic_version"
                )
                refs = await references(restored, manifest["buckets"])

            def canonical(values):
                return sorted(json.dumps(row, sort_keys=True) for row in values)

            if (
                counts != manifest["table_counts"]
                or schema != manifest["schema_version"]
                or canonical(refs) != canonical(manifest["references"])
            ):
                raise RecoveryError(
                    "Restored schema, table counts or object references differ from the source snapshot"
                )
            result["tables_verified"] = len(counts)
            result["schema_version"] = schema
        finally:
            await restored.close()
        result["bucket_mapping"] = {
            source: f"vg-restore-{drill_id[:20]}-{role}"
            for role, source in manifest["buckets"].items()
        }
        await asyncio.to_thread(
            restore_objects, client, root, manifest, result["bucket_mapping"], timeout
        )
        result.update(
            status="restore_verified",
            objects_verified=len(manifest["objects"]),
            references_verified=len(refs),
        )
        return result
    except Exception as exc:
        result["error"] = (
            str(exc)
            if isinstance(exc, RecoveryError)
            else "Recovery operation failed; review isolated target and credentials"
        )
        raise
    finally:
        if admin is not None:
            await admin.close()
        result["finished_at"] = utc()
        result["drill_seconds"] = round(time.monotonic() - start, 3)
        temporary_report = report.with_name(report.name + ".pending-" + uuid4().hex)
        write_json(temporary_report, result)
        temporary_report.replace(report)
        sync_directory(report.parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument(
        "--output",
        type=Path,
        default=Path("backups")
        / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid4().hex[:8]
        ),
    )
    verify = sub.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--manifest-sha256")
    drill = sub.add_parser("drill")
    drill.add_argument("--bundle", type=Path, required=True)
    drill.add_argument("--manifest-sha256", required=True)
    drill.add_argument("--report", type=Path, required=True)
    for command in (create, drill):
        command.add_argument(
            "--pg-client-image",
            help="Optional Linux host-network Docker image supplying PostgreSQL clients",
        )
        command.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == "verify":
            manifest = verify_bundle(args.bundle, args.manifest_sha256)
            result = {
                "status": "integrity_verified",
                "objects": len(manifest["objects"]),
                "production_approved": False,
            }
        elif args.command == "create":
            buckets = {
                role: os.environ.get("BACKUP_BUCKET_" + role.upper(), role)
                for role in BUCKET_ROLES
            }
            result = asyncio.run(
                create_backup(
                    args.output,
                    database_url("BACKUP_DATABASE_URL"),
                    s3_client("BACKUP"),
                    buckets,
                    args.pg_client_image,
                    args.timeout,
                )
            )
        else:
            result = asyncio.run(
                restore_drill(
                    args.bundle,
                    args.manifest_sha256,
                    database_url("RESTORE_ADMIN_DATABASE_URL"),
                    s3_client("RESTORE"),
                    args.report,
                    args.pg_client_image,
                    args.timeout,
                )
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": str(exc)
                    if isinstance(exc, RecoveryError)
                    else "Operation failed; no verified completion was recorded. Check environment, tool versions and private destination access.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
