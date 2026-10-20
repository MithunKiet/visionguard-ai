"""Backup corruption/target guards and isolated PostgreSQL/S3 protocol recovery."""

import asyncio
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit
from uuid import uuid4
from xml.sax.saxutils import escape

import asyncpg
from minio import Minio
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("backup_recovery", ROOT / "infra/backup/recovery.py")
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "backup"
    root.mkdir()
    (root / "objects").mkdir()
    (root / "postgres.dump").write_bytes(b"synthetic dump for integrity tests only")
    (root / "objects/00000000.bin").write_bytes(b"photo")
    manifest = {
        "format": 1,
        "status": "complete",
        "schema_version": "0025",
        "table_counts": {"public.example": 1},
        "buckets": dict(zip(recovery.BUCKET_ROLES, recovery.BUCKET_ROLES)),
        "database": {"path": "postgres.dump", **recovery.digest_file(root / "postgres.dump")},
        "objects": [
            {
                "path": "objects/00000000.bin",
                "bucket": "snapshots",
                "key": "../camera/photo",
                "content_type": "image/jpeg",
                **recovery.digest_file(root / "objects/00000000.bin"),
            }
        ],
        "references": [{"bucket": "snapshots", "key": "../camera/photo"}],
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root, manifest


def save_manifest(bundle):
    (bundle[0] / "manifest.json").write_text(json.dumps(bundle[1]))


def test_valid_bundle_and_cli_do_not_claim_restore_or_production_acceptance(bundle):
    root, _ = bundle
    assert recovery.verify_bundle(root)["status"] == "complete"
    process = subprocess.run(
        [sys.executable, str(ROOT / "infra/backup/recovery.py"), "verify", "--bundle", str(root)],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0
    assert json.loads(process.stdout) == {"status": "integrity_verified", "objects": 1, "production_approved": False}


@pytest.mark.parametrize(
    "damage",
    [
        "dump",
        "object",
        "missing_object",
        "missing_manifest",
        "extra_file",
        "symlink",
        "traversal",
        "duplicate_object",
        "missing_reference",
        "wrong_evidence_hash",
        "wrong_evidence_size",
        "incomplete",
        "negative_count",
        "duplicate_json",
    ],
)
def test_corrupt_or_unsafe_bundle_fails(bundle, damage):
    root, manifest = bundle
    if damage == "dump":
        (root / "postgres.dump").write_bytes(b"changed")
    elif damage == "object":
        (root / "objects/00000000.bin").write_bytes(b"changed")
    elif damage == "missing_object":
        (root / "objects/00000000.bin").unlink()
    elif damage == "missing_manifest":
        (root / "manifest.json").unlink()
    elif damage == "extra_file":
        (root / "unexpected").write_text("extra")
    elif damage == "symlink":
        (root / "objects/00000000.bin").unlink()
        (root / "objects/00000000.bin").symlink_to(root / "postgres.dump")
    elif damage == "traversal":
        manifest["objects"][0]["path"] = "../elsewhere"
    elif damage == "duplicate_object":
        manifest["objects"].append(dict(manifest["objects"][0]))
    elif damage == "missing_reference":
        manifest["references"][0]["key"] = "absent"
    elif damage == "wrong_evidence_hash":
        manifest["references"][0]["sha256"] = "a" * 64
    elif damage == "wrong_evidence_size":
        manifest["references"][0]["size"] = 100
    elif damage == "incomplete":
        manifest["status"] = "copying"
    elif damage == "negative_count":
        manifest["table_counts"]["public.example"] = -1
    elif damage == "duplicate_json":
        (root / "manifest.json").write_text('{"format":1,"format":1}')
    if damage not in {"missing_manifest", "duplicate_json"}:
        save_manifest(bundle)
    with pytest.raises(recovery.RecoveryError):
        recovery.verify_bundle(root)


def test_independent_manifest_checksum_detects_modified_inventory(bundle):
    root, manifest = bundle
    original = recovery.digest_file(root / "manifest.json")["sha256"]
    manifest["table_counts"]["public.example"] = 3
    save_manifest(bundle)
    with pytest.raises(recovery.RecoveryError, match="independently retained"):
        recovery.verify_bundle(root, original)


async def test_existing_report_or_nonmaintenance_target_rejected_before_connection(bundle, tmp_path, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Must not connect")

    monkeypatch.setattr(recovery.asyncpg, "connect", forbidden)
    root, _ = bundle
    checksum = recovery.digest_file(root / "manifest.json")["sha256"]
    with pytest.raises(recovery.RecoveryError, match="maintenance"):
        await recovery.restore_drill(
            root, checksum, "postgresql://user@localhost/live_database", None, tmp_path / "report.json"
        )
    report = tmp_path / "existing.json"
    report.write_text("keep")
    with pytest.raises(recovery.RecoveryError, match="new report"):
        await recovery.restore_drill(root, checksum, "postgresql://user@localhost/postgres", None, report)
    assert report.read_text() == "keep"


def test_credentials_stay_out_of_process_arguments(monkeypatch):
    monkeypatch.setenv("PGSERVICE", "unrelated")
    url = "postgresql://test:private%24password@localhost:5432/sample?sslmode=require"
    env = recovery.pg_env(url)
    assert env["PGPASSWORD"] == "private$password" and "PGSERVICE" not in env
    command = recovery.pg_command("pg_dump", ["--format=custom"], "postgres:16-alpine", "test-only")
    assert not any("private" in value for value in command)
    assert env["PGSSLMODE"] == "require"


def test_insecure_remote_storage_rejected(monkeypatch):
    for key, value in {
        "ENDPOINT": "remote.invalid:9000",
        "ACCESS_KEY": "test",
        "SECRET_KEY": "test",
        "LOCAL_HTTP": "1",
    }.items():
        monkeypatch.setenv("BACKUP_S3_" + key, value)
    with pytest.raises(recovery.RecoveryError, match="loopback"):
        recovery.s3_client("BACKUP")


@pytest.fixture
def s3():
    """Real SDK transport only; this fixture does not validate provider auth/TLS."""
    objects = {role: {} for role in recovery.BUCKET_ROLES}
    objects["snapshots"]["factory/proof.png"] = b"original evidence bytes"
    objects["reports"]["factory/report.pdf"] = b"original report bytes"

    def etag(content):
        return hashlib.md5(content).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def route(self):
            parts = urlsplit(self.path)
            bucket, _, key = unquote(parts.path.lstrip("/")).partition("/")
            return bucket, key, parse_qs(parts.query)

        def reply(self, status, content=b"", content_type="application/octet-stream", tag=None):
            self.send_response(status)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Content-Type", content_type)
            if tag:
                self.send_header("ETag", '"' + tag + '"')
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(content)

        def do_HEAD(self):
            bucket, key, _ = self.route()
            self.reply(200 if bucket in objects and (not key or key in objects[bucket]) else 404)

        def do_GET(self):
            bucket, key, query = self.route()
            if bucket not in objects:
                return self.reply(404)
            if query.get("list-type") == ["2"]:
                contents = "".join(
                    "<Contents><Key>"
                    + escape(k)
                    + '</Key><LastModified>2026-10-20T00:00:00.000Z</LastModified><ETag>"'
                    + etag(v)
                    + '"</ETag><Size>'
                    + str(len(v))
                    + "</Size><StorageClass>STANDARD</StorageClass></Contents>"
                    for k, v in sorted(objects[bucket].items())
                )
                xml = (
                    '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Name>'
                    + bucket
                    + "</Name><IsTruncated>false</IsTruncated>"
                    + contents
                    + "</ListBucketResult>"
                )
                return self.reply(200, xml.encode(), "application/xml")
            if key not in objects[bucket]:
                return self.reply(404)
            self.reply(200, objects[bucket][key], tag=etag(objects[bucket][key]))

        def do_PUT(self):
            bucket, key, _ = self.route()
            content = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if not key:
                if bucket in objects:
                    return self.reply(409)
                objects[bucket] = {}
                return self.reply(200)
            if bucket not in objects:
                return self.reply(404)
            objects[bucket][key] = content
            self.reply(200, tag=etag(content))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = Minio(
        f"127.0.0.1:{server.server_port}", access_key="fixture", secret_key="fixture", secure=False, region="us-east-1"
    )
    yield SimpleNamespace(client=client, objects=objects)
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_real_sdk_copies_opaque_keys_and_detects_inventory_change(s3, tmp_path):
    buckets = dict(zip(recovery.BUCKET_ROLES, recovery.BUCKET_ROLES))
    s3.objects["snapshots"]["C:/outside"] = b"opaque object key"
    entries = recovery.copy_objects(s3.client, buckets, tmp_path)
    assert len(entries) == 3
    assert all((tmp_path / entry["path"]).is_file() for entry in entries)
    assert not (tmp_path.parent / "outside").exists()
    original = s3.client.list_objects
    calls = 0

    def changed(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 5:
            s3.objects["snapshots"]["factory/proof.png"] = b"overwritten"
        return original(*args, **kwargs)

    s3.client.list_objects = changed
    other = tmp_path / "changing"
    other.mkdir()
    with pytest.raises(recovery.RecoveryError, match="changed or disappeared"):
        recovery.copy_objects(s3.client, buckets, other)


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Requires disposable PostgreSQL and matching native clients or TEST_BACKUP_PG_CLIENT_IMAGE",
)
async def test_actual_snapshot_backup_and_isolated_restore(tmp_path, s3, monkeypatch):
    from src.shared.database.models import Alert, AuditLog, CorrectiveEvidence, Enterprise, PPEViolation, Report

    base = os.environ["TEST_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    parts = urlsplit(base)
    admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, ""))
    source_name = "vg_" + uuid4().hex + "_backup_test"
    source_url = urlunsplit((parts.scheme, parts.netloc, "/" + source_name, parts.query, ""))
    image = os.environ.get("TEST_BACKUP_PG_CLIENT_IMAGE")
    admin = await asyncpg.connect(admin_url)
    created = [source_name]
    await admin.execute(f'CREATE DATABASE "{source_name}"')
    try:
        env = {
            **os.environ,
            "DATABASE_URL": source_url.replace("postgresql://", "postgresql+asyncpg://"),
            "DEBUG": "false",
        }
        process = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "backend",
            env=env,
            capture_output=True,
            timeout=90,
        )
        assert process.returncode == 0, "Isolated fixture migrations failed"
        engine = create_async_engine(env["DATABASE_URL"])
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            enterprise = Enterprise(name="Restore fixture", code=uuid4().hex)
            db.add(enterprise)
            await db.flush()
            alert = Alert(
                enterprise_id=enterprise.id,
                alert_number="RESTORE-" + uuid4().hex[:12],
                alert_type="PPE",
                severity="High",
                status="Open",
            )
            db.add(alert)
            await db.flush()
            evidence = s3.objects["snapshots"]["factory/proof.png"]
            db.add_all(
                [
                    PPEViolation(
                        enterprise_id=enterprise.id,
                        violation_type="helmet",
                        confidence=0.8,
                        snapshot_key="factory/proof.png",
                    ),
                    CorrectiveEvidence(
                        enterprise_id=enterprise.id,
                        alert_id=alert.id,
                        plan_version=1,
                        object_key="factory/proof.png",
                        filename="proof.png",
                        content_type="image/png",
                        size_bytes=len(evidence),
                        sha256=hashlib.sha256(evidence).hexdigest(),
                    ),
                    Report(
                        enterprise_id=enterprise.id,
                        report_type="PPE",
                        format="PDF",
                        from_date=datetime.now(timezone.utc),
                        to_date=datetime.now(timezone.utc),
                        object_key="factory/report.pdf",
                        status="Completed",
                    ),
                    AuditLog(enterprise_id=enterprise.id, action="RECOVERY_FIXTURE"),
                ]
            )
            await db.commit()
        await engine.dispose()
        original = recovery.run_pg

        def concurrent_source_write(tool, args, url, **kwargs):
            if tool == "pg_dump":

                async def change():
                    connection = await asyncpg.connect(source_url)
                    await connection.execute("UPDATE enterprises SET name = 'Changed after snapshot'")
                    await connection.execute("CREATE TABLE public.after_snapshot (id integer)")
                    await connection.close()

                asyncio.run(change())
            return original(tool, args, url, **kwargs)

        monkeypatch.setattr(recovery, "run_pg", concurrent_source_write)
        root = tmp_path / "backup"
        result = await recovery.create_backup(
            root,
            source_url,
            s3.client,
            dict(zip(recovery.BUCKET_ROLES, recovery.BUCKET_ROLES)),
            image=image,
            timeout=60,
        )
        assert result["status"] == "backup_complete"
        manifest = recovery.verify_bundle(root, result["manifest_sha256"])
        assert "public.after_snapshot" not in manifest["table_counts"]
        report = tmp_path / "restore-report.json"
        restored = await recovery.restore_drill(
            root, result["manifest_sha256"], admin_url, s3.client, report, image=image, timeout=60
        )
        created.append(restored["database"])
        assert restored["status"] == "restore_verified" and restored["references_verified"] == 3
        assert (
            restored["objects_verified"] == 2
            and not restored["production_approved"]
            and not restored["services_started"]
        )
        target_url = urlunsplit((parts.scheme, parts.netloc, "/" + restored["database"], parts.query, ""))
        connection = await asyncpg.connect(target_url)
        assert await connection.fetchval("SELECT name FROM enterprises") == "Restore fixture"
        with pytest.raises(asyncpg.RaiseError, match="append-only"):
            await connection.execute("DELETE FROM audit.audit_log WHERE false")
        await connection.close()
        for role, target in restored["bucket_mapping"].items():
            assert s3.objects[target] == s3.objects[role]
        assert json.loads(report.read_text())["status"] == "restore_verified"
        assert (root.stat().st_mode & 0o077) == 0
    finally:
        # Test-owned random databases only; production tooling never drops destinations.
        for report in tmp_path.glob("*report.json"):
            value = json.loads(report.read_text()).get("database", "")
            if re.fullmatch(r"vg_restore_[a-f0-9]{32}", value) and value not in created:
                created.append(value)
        for name in created:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


def test_new_objects_do_not_invalidate_existing_snapshot_copy(s3, tmp_path):
    original = s3.client.list_objects
    calls = 0

    def added(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 5:
            s3.objects["snapshots"]["later-arrival"] = b"new event after snapshot"
        return original(*args, **kwargs)

    s3.client.list_objects = added
    entries = recovery.copy_objects(s3.client, dict(zip(recovery.BUCKET_ROLES, recovery.BUCKET_ROLES)), tmp_path)
    assert len(entries) == 2 and all(row["key"] != "later-arrival" for row in entries)


def test_existing_restore_bucket_is_never_reused(bundle, s3):
    mapping = {name: name for name in recovery.BUCKET_ROLES}
    before = {key: dict(value) for key, value in s3.objects.items()}
    with pytest.raises(recovery.RecoveryError, match="already exists"):
        recovery.restore_objects(s3.client, bundle[0], bundle[1], mapping)
    assert s3.objects == before


def test_read_back_corruption_blocks_verified_restore(bundle, s3, monkeypatch):
    root, manifest = bundle
    # Use a legal S3 key; local paths still come exclusively from opaque artifact names.
    manifest["objects"][0]["key"] = "photo"
    original = s3.client.get_object

    def corrupted(bucket, key):
        if bucket.startswith("vg-restore-"):
            s3.objects[bucket][key] = b"corrupted bytes"
        return original(bucket, key)

    monkeypatch.setattr(s3.client, "get_object", corrupted)
    mapping = {name: "vg-restore-" + uuid4().hex + "-" + name for name in recovery.BUCKET_ROLES}
    with pytest.raises(recovery.RecoveryError, match="read-back"):
        recovery.restore_objects(s3.client, root, manifest, mapping)


async def test_failed_database_restore_records_failure_without_object_writes(bundle, tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    admin = SimpleNamespace(execute=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(recovery.asyncpg, "connect", AsyncMock(return_value=admin))

    def fail(*args, **kwargs):
        raise recovery.RecoveryError("pg_restore failed; backup/restore is incomplete")

    monkeypatch.setattr(recovery, "run_pg", fail)
    root, _ = bundle
    report = tmp_path / "failure.json"
    with pytest.raises(recovery.RecoveryError, match="pg_restore failed"):
        await recovery.restore_drill(
            root,
            recovery.digest_file(root / "manifest.json")["sha256"],
            "postgresql://user@localhost/postgres",
            None,
            report,
        )
    result = json.loads(report.read_text())
    assert result["status"] == "failed" and result["database_created"]
    assert result["bucket_mapping"] == {} and not result["services_started"]
    sql = [call.args[0] for call in admin.execute.call_args_list]
    assert len(sql) == 2 and sql[0].startswith('CREATE DATABASE "vg_restore_')
    assert all("DROP" not in statement for statement in sql)


async def test_missing_evidence_never_publishes_completion(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock()
    transaction.__aexit__ = AsyncMock(return_value=False)
    connection = SimpleNamespace(
        transaction=lambda **kwargs: transaction,
        fetchval=AsyncMock(side_effect=["snapshot-test", "0025"]),
        close=AsyncMock(),
    )
    monkeypatch.setattr(recovery.asyncpg, "connect", AsyncMock(return_value=connection))
    monkeypatch.setattr(recovery, "table_counts", AsyncMock(return_value={"public.example": 1}))
    monkeypatch.setattr(recovery, "references", AsyncMock(return_value=[{"bucket": "snapshots", "key": "missing"}]))

    def dump(*args, **kwargs):
        kwargs["output_path"].write_bytes(b"test-only dump")

    def no_objects(client, buckets, root, timeout):
        (root / "objects").mkdir()
        return []

    monkeypatch.setattr(recovery, "run_pg", dump)
    monkeypatch.setattr(recovery, "copy_objects", no_objects)
    root = tmp_path / "incomplete"
    with pytest.raises(recovery.RecoveryError, match="absent"):
        await recovery.create_backup(
            root, "postgresql://test@localhost/test", None, dict(zip(recovery.BUCKET_ROLES, recovery.BUCKET_ROLES))
        )
    assert not (root / "manifest.json").exists()
    assert (root / "manifest.pending.json").exists()
    with pytest.raises(recovery.RecoveryError, match="completion manifest"):
        recovery.verify_bundle(root)


def test_timeout_removes_only_its_named_client_container(tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(command, 1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(recovery.subprocess, "run", run)
    with pytest.raises(recovery.RecoveryError, match="time budget"):
        recovery.run_pg(
            "pg_dump",
            [],
            "postgresql://test@localhost/test",
            image="postgres:16-alpine",
            output_path=tmp_path / "partial.dump",
            timeout=1,
        )
    name = calls[0][calls[0].index("--name") + 1]
    assert re.fullmatch(r"vg-recovery-client-[a-f0-9]{32}", name)
    assert calls[1] == ["docker", "rm", "-f", name]
