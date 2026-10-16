"""Synthetic control-plane measurement on an EMPTY *_capacity_test database.

Runs real loopback HTTP, RabbitMQ confirms/consumer and PostgreSQL transactions.
No cameras, inference, evidence upload or notification delivery are started.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import hashlib
from importlib.metadata import version
import resource
import math
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import time
from uuid import uuid4


def percentile(values, fraction=.95):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def summary(values):
    return {"count": len(values), "p50_ms": percentile(values, .5), "p95_ms": percentile(values), "max_ms": max(values) if values else None}


def source_identity():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted((root / "src").rglob("*.py")) + [Path(__file__).resolve()]:
        digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes())
    return {"backend_source_sha256": digest.hexdigest(),
        "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
        "packages": {name: version(name) for name in ("fastapi", "uvicorn", "sqlalchemy", "asyncpg", "aio-pika", "httpx")},
        "host_logical_cpus": os.cpu_count(), "architecture": platform.machine(),
        "cgroup_cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip() if Path("/sys/fs/cgroup/cpu.max").exists() else None,
        "cgroup_memory_max": Path("/sys/fs/cgroup/memory.max").read_text().strip() if Path("/sys/fs/cgroup/memory.max").exists() else None}


def validate_args(args):
    db_url = os.environ.get("CAPACITY_DATABASE_URL", "")
    from sqlalchemy.engine import make_url
    if make_url(db_url).database is None or not make_url(db_url).database.endswith("_capacity_test"):
        raise ValueError("Use a dedicated empty *_capacity_test database")
    if os.environ.get("ENVIRONMENT", "development") == "production":
        raise ValueError("Run in an isolated measurement environment")
    if not (1 <= args.factories <= 10 and 1 <= args.cameras_per_factory <= 200
            and 1 <= args.workers_per_factory <= args.cameras_per_factory
            and args.cameras_per_factory % args.workers_per_factory == 0
            and 5 <= args.seconds <= 300 and 1 <= args.events_per_second <= 100
            and 1 <= args.reads_per_second <= 30 and 1 <= args.history_events <= 10000
            and 1 <= args.history_cameras <= 2000):
        raise ValueError("Invalid bounded workload settings")
    if not all(math.isfinite(value) and value > 0 for value in (args.p95_ms, args.event_p95_ms)):
        raise ValueError("Latency gates must be positive")
    os.environ["DATABASE_URL"] = db_url
    os.environ["DEBUG"] = "false"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def measure(args):
    import aio_pika
    import httpx
    from sqlalchemy import event as sql_event, func, select
    import uvicorn
    from src.core.app import create_app
    from src.core.settings import settings
    from src.modules.identity.application.services import AuthService
    from src.modules.identity.infrastructure.repositories import UserRepository
    from src.shared.cache.client import init_redis, close_redis
    from src.shared.database.models import (AIWorker, Alert, Camera, Department, Enterprise, EventReceipt,
        Factory, NotificationDelivery, PPEViolation, Role, User, UserRole, Zone, ZoneConfig)
    from src.shared.database.session import AsyncSessionFactory, engine, init_db
    from src.shared.messaging.consumer import _dispatch_event

    runtime = source_identity()
    await init_db()
    async with AsyncSessionFactory() as db:
        if await db.scalar(select(func.count()).select_from(Enterprise)):
            raise ValueError("Database must have no enterprises; use a fresh migrated test database")
    await init_redis()
    run_id = uuid4().hex
    workers, cameras = [], []
    async with AsyncSessionFactory() as db:
        tenant = Enterprise(name="Synthetic fleet benchmark", code=run_id)
        db.add(tenant)
        await db.flush()
        for i in range(args.factories):
            factory = Factory(enterprise_id=tenant.id, name=f"Synthetic factory {i}", code=f"f{i}")
            db.add(factory)
            await db.flush()
            department = Department(enterprise_id=tenant.id, factory_id=factory.id, name="Synthetic", code=f"d{i}")
            db.add(department)
            await db.flush()
            zone = Zone(enterprise_id=tenant.id, factory_id=factory.id, department_id=department.id, name="Synthetic", code=f"z{i}", max_occupancy=100)
            db.add(zone)
            await db.flush()
            db.add(ZoneConfig(enterprise_id=tenant.id, zone_id=zone.id))
            for j in range(args.workers_per_factory):
                worker = AIWorker(enterprise_id=tenant.id, factory_id=factory.id,
                    worker_id=f"capacity-{run_id[:8]}-{i}-{j}", max_cameras=args.cameras_per_factory // args.workers_per_factory,
                    status="Online", last_heartbeat=datetime.now(timezone.utc))
                db.add(worker)
                await db.flush()
                workers.append({"row": worker, "session": str(uuid4()), "key": uuid4().hex})
                for k in range(worker.max_cameras):
                    camera = Camera(enterprise_id=tenant.id, factory_id=factory.id, zone_id=zone.id,
                        worker_id=worker.id, name="Synthetic camera", code=f"c{i}-{j}-{k}", rtsp_url="rtsp://unused.invalid/feed")
                    db.add(camera)
                    cameras.append(camera)
        user = User(enterprise_id=tenant.id, name="Benchmark reader", email=f"{run_id}@example.invalid",
            password_hash="unusable-benchmark-login", is_first_login=False, status="Active")
        db.add(user)
        await db.flush()
        role = await db.scalar(select(Role).where(Role.code == "ENTERPRISE_ADMIN"))
        db.add(UserRole(user_public_id=user.public_id, role_public_id=role.public_id))
        await db.commit()
        token = AuthService(db)._make_access_token(await UserRepository(db).get_by_id(user.public_id))
    settings.WORKER_CREDENTIALS = {w["row"].worker_id: {"key": w["key"], "enterprise_id": tenant.public_id} for w in workers}
    # No lifespan means no provider/outbox worker, production consumers or MinIO.
    app = create_app()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", access_log=False, log_level="warning"))
    server_task = asyncio.create_task(server.serve(sockets=[sock]))
    connection = None
    queue = exchange = None
    grants = {}
    latencies = defaultdict(list)
    failures = Counter()
    sent_at, finished_ids = {}, set()
    callback_tasks = set()
    event_latencies = []
    samples = {"sql_statements": 0, "pool_peak_checked_out": 0, "broker_peak_ready": 0, "broker_peak_inflight": 0}
    checked_out = 0
    measuring = False
    def statement(*unused):
        if measuring:
            samples["sql_statements"] += 1
    def checkout(*unused):
        nonlocal checked_out
        checked_out += 1
        if measuring:
            samples["pool_peak_checked_out"] = max(samples["pool_peak_checked_out"], checked_out)
    def checkin(*unused):
        nonlocal checked_out
        checked_out -= 1
    sql_event.listen(engine.sync_engine, "before_cursor_execute", statement)
    sql_event.listen(engine.sync_engine, "checkout", checkout)
    sql_event.listen(engine.sync_engine, "checkin", checkin)
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if server_task.done():
                    await server_task
                    raise RuntimeError("Loopback API failed to start")
                await asyncio.sleep(.05)
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL, timeout=10)
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        await channel.set_qos(prefetch_count=10)
        exchange = await channel.declare_exchange(f"capacity.{run_id}", aio_pika.ExchangeType.DIRECT, auto_delete=True)
        queue = await channel.declare_queue(f"capacity.{run_id}", auto_delete=True)
        await queue.bind(exchange, "events.helmet_missing_detected")
        async def consume(message):
            task = asyncio.current_task()
            callback_tasks.add(task)
            if measuring:
                samples["broker_peak_inflight"] = max(samples["broker_peak_inflight"], len(callback_tasks))
            event_id = json.loads(message.body)["event_id"]
            if message.redelivered:
                failures["consumer_redelivery"] += 1
            try:
                await _dispatch_event(message)
                if event_id not in finished_ids and event_id in sent_at:
                    event_latencies.append((time.perf_counter() - sent_at[event_id]) * 1000)
                finished_ids.add(event_id)
            except Exception as error:
                failures[f"consumer_{type(error).__name__}"] += 1
            finally:
                callback_tasks.discard(task)
        await queue.consume(consume)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=20, follow_redirects=False) as client:
            async def request(method, path, *, label, **kwargs):
                start = time.perf_counter()
                response = await client.request(method, path, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                if measuring:
                    latencies[label].append(elapsed)
                response.raise_for_status()
                data = response.json()
                if not data.get("success") or not isinstance(data.get("data"), (list, dict)):
                    raise ValueError("Invalid API envelope")
                return data
            async def renew(worker):
                row = worker["row"]
                headers = {"X-Worker-Key": worker["key"], "X-Enterprise-Id": tenant.public_id,
                    "X-Worker-Session": worker["session"]}
                await request("POST", "/api/v1/workers/heartbeat", label="heartbeat", headers=headers,
                    json={"worker_id": row.worker_id, "model_version": "synthetic-control-plane", "gpu_available": False})
                data = await request("GET", f"/api/v1/workers/{row.worker_id}/cameras", label="assignments", headers=headers)
                if len(data["data"]) != row.max_cameras:
                    raise ValueError("Wrong assignment count")
                for camera in data["data"]:
                    grants[camera["camera_id"]] = (camera, row.worker_id, time.perf_counter())
            await asyncio.gather(*(renew(w) for w in workers))
            async def emit(index, timed):
                history_cameras = min(args.history_cameras, len(cameras))
                camera_index = index % len(cameras) if timed else (index % history_cameras) * len(cameras) // history_cameras
                camera = cameras[camera_index]
                assignment, worker_id, received = grants[camera.public_id]
                lease = assignment["lease"]
                observed = datetime.fromisoformat(lease["server_time"]) + timedelta(seconds=time.perf_counter() - received)
                if observed >= datetime.fromisoformat(lease["expires_at"]):
                    raise ValueError("Benchmark worker failed to renew its lease")
                event_id = str(uuid4())
                body = {"event_id": event_id, "worker_id": worker_id, "camera_id": camera.public_id,
                    "enterprise_id": tenant.public_id, "factory_id": assignment["factory_id"], "zone_id": assignment["zone_id"],
                    "confidence": .95, "timestamp": datetime.now(timezone.utc).isoformat(), "track_id": index, "bbox": [1, 2, 3, 4],
                    "camera_lease": {"token": lease["token"], "session_id": lease["session_id"], "generation": lease["generation"],
                        "observed_at": observed.isoformat()}}
                if timed:
                    sent_at[event_id] = time.perf_counter()
                await exchange.publish(aio_pika.Message(body=json.dumps(body).encode(), message_id=event_id,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT), routing_key="events.helmet_missing_detected", mandatory=True, timeout=10)
            # Populate real violations/alerts before read latency measurements.
            for index in range(args.history_events):
                await emit(index, False)
                if index % 100 == 0:
                    await asyncio.gather(*(renew(w) for w in workers))
            async with asyncio.timeout(120):
                while len(finished_ids) < args.history_events:
                    if failures:
                        raise RuntimeError("Warmup event failed")
                    await asyncio.sleep(.05)
            await asyncio.gather(*(renew(w) for w in workers))
            async with AsyncSessionFactory() as db:
                initial_alerts = await db.scalar(select(func.count()).select_from(Alert).where(Alert.enterprise_id == tenant.id))
            before_count = len(finished_ids)
            start = time.perf_counter()
            deadline = start + args.seconds
            measuring = True
            async def produce():
                for index in range(args.seconds * args.events_per_second):
                    await asyncio.sleep(max(0, start + index / args.events_per_second - time.perf_counter()))
                    if time.perf_counter() >= deadline:
                        failures["event_schedule_not_met"] += args.seconds * args.events_per_second - index
                        break
                    await emit(args.history_events + index, True)
            async def read_one(index):
                route = ("alerts?page_size=50", "violations?page_size=50", "cameras")[index % 3]
                try:
                    data = await request("GET", f"/api/v1/{route}", label=route.split("?")[0], headers={"Authorization": f"Bearer {token}"})
                    minimum = len(cameras) if route == "cameras" else min(1, args.history_events)
                    if len(data["data"]) < minimum:
                        raise ValueError("Unexpected empty or incomplete dataset")
                except Exception as error:
                    failures[f"api_{type(error).__name__}"] += 1
            async def readers():
                pending = set()
                for index in range(args.seconds * args.reads_per_second):
                    await asyncio.sleep(max(0, start + index / args.reads_per_second - time.perf_counter()))
                    if time.perf_counter() >= deadline or len(pending) >= 30:
                        failures["read_schedule_not_met"] += 1
                        continue
                    task = asyncio.create_task(read_one(index))
                    pending.add(task)
                    task.add_done_callback(pending.discard)
                await asyncio.gather(*pending)
            async def pollers():
                for tick in range(math.ceil(args.seconds / 30)):
                    await asyncio.sleep(max(0, start + tick * 30 - time.perf_counter()))
                    await asyncio.gather(*(renew(w) for w in workers))
            async def sample_queue():
                while time.perf_counter() < deadline:
                    declared = await channel.declare_queue(queue.name, passive=True)
                    samples["broker_peak_ready"] = max(samples["broker_peak_ready"], declared.declaration_result.message_count)
                    await asyncio.sleep(.5)
            await asyncio.gather(produce(), readers(), pollers(), sample_queue())
            backlog_at_end = len(sent_at) - (len(finished_ids) - before_count)
            async with asyncio.timeout(60):
                while len(finished_ids) - before_count < len(sent_at):
                    if failures:
                        break
                    await asyncio.sleep(.05)
            drained_seconds = time.perf_counter() - start
            measuring = False
            async with AsyncSessionFactory() as db:
                receipt_count = await db.scalar(select(func.count()).select_from(EventReceipt).where(EventReceipt.event_id.in_(list(sent_at))))
                persisted = await db.scalar(select(func.count()).select_from(PPEViolation).where(PPEViolation.enterprise_id == tenant.id))
                alerts = await db.scalar(select(func.count()).select_from(Alert).where(Alert.enterprise_id == tenant.id))
                deliveries = await db.scalar(select(func.count()).select_from(NotificationDelivery).where(NotificationDelivery.enterprise_id == tenant.id))
            if receipt_count != len(sent_at) or persisted != args.history_events + len(sent_at):
                failures["persisted_count_mismatch"] += 1
            if len(sent_at) != args.seconds * args.events_per_second:
                failures["offered_event_count_mismatch"] += 1
            if any(percentile(values) >= args.p95_ms for values in latencies.values()) or not latencies:
                failures["api_p95_gate"] += 1
            if not event_latencies or percentile(event_latencies) >= args.event_p95_ms:
                failures["event_p95_gate"] += 1
            return {"scope": "synthetic_control_plane", "status": "pass" if not failures else "fail",
                "production_approved": False, "camera_detection_capacity_measured": False,
                "created_at": datetime.now(timezone.utc).isoformat(), "git_revision": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], text=True).strip(), "python": platform.python_version(),
                "runtime": runtime, "api_and_generator_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "workload": vars(args) | {"output": str(args.output)}, "cameras": len(cameras), "workers": len(workers),
                "measurement_seconds": args.seconds, "elapsed_including_drain_seconds": drained_seconds,
                "events_published": len(sent_at), "timed_event_receipts": receipt_count,
                "total_persisted_violations": persisted, "total_persisted_alerts": alerts, "timed_alerts_created": alerts - initial_alerts,
                "total_outbox_rows": deliveries,
                "api_latency": {key: summary(value) for key, value in latencies.items()},
                "publish_to_handler_completion": summary(event_latencies), "backlog_at_load_end": backlog_at_end,
                "failures": dict(failures), "database_and_broker": samples,
                "limitations": ["Synthetic metadata; no GPU, RTSP, evidence or notification delivery",
                    "Load generator and API share a process; loopback HTTP excludes production TLS/proxy/network",
                    "Private auto-delete benchmark queue; confirms tested, broker restart durability not tested",
                    "Short synthetic dataset/run; not production capacity or a site soak"]}
    finally:
        measuring = False
        if queue:
            await queue.delete(if_unused=False, if_empty=False)
        if exchange:
            await exchange.delete(if_unused=False)
        if connection:
            await connection.close()
        if callback_tasks:
            await asyncio.gather(*callback_tasks, return_exceptions=True)
        server.should_exit = True
        await server_task
        sock.close()
        sql_event.remove(engine.sync_engine, "before_cursor_execute", statement)
        sql_event.remove(engine.sync_engine, "checkout", checkout)
        sql_event.remove(engine.sync_engine, "checkin", checkin)
        await close_redis()
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factories", type=int, default=5)
    parser.add_argument("--cameras-per-factory", type=int, default=200)
    parser.add_argument("--workers-per-factory", type=int, default=4)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--events-per-second", type=int, default=10)
    parser.add_argument("--reads-per-second", type=int, default=6)
    parser.add_argument("--history-events", type=int, default=1000)
    parser.add_argument("--history-cameras", type=int, default=100)
    parser.add_argument("--p95-ms", type=float, default=750)
    parser.add_argument("--event-p95-ms", type=float, default=2000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = None
    try:
        validate_args(args)
        async def bounded():
            async with asyncio.timeout(args.seconds + 300):
                return await measure(args)
        result = asyncio.run(bounded())
    except Exception as error:
        result = {"status": "error", "scope": "synthetic_control_plane", "error_type": type(error).__name__, "production_approved": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Control-plane measurement: {result['status']}. Report: {args.output}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
