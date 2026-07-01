"""
Publish a synthetic PPE violation event directly to RabbitMQ, mimicking what
the AI Worker would send. Useful for demoing the full pipeline (consumer ->
DB -> alert -> WebSocket -> frontend) without a fine-tuned PPE model, since
the stock YOLO fallback only detects "person" and never emits real violations.

Usage (run from backend/ directory):
    python -m scripts.publish_test_violation --enterprise-id <uuid> --zone-id <uuid> \
        --camera-id <uuid> --factory-id <uuid> [--type helmet_missing] [--confidence 0.87]

Get the ids from seed_demo_pilot.py output or GET /api/v1/cameras.
"""
import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import aio_pika
import json

from src.core.settings import settings


async def publish(args: argparse.Namespace) -> None:
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    channel = await connection.channel()
    exchange = await channel.declare_exchange(
        "ai_worker_events", aio_pika.ExchangeType.TOPIC, durable=True
    )

    routing_key = f"events.{args.type}_detected"
    body = {
        "event": f"{args.type}_detected",
        "event_id": str(uuid.uuid4()),
        "worker_id": "manual-test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "enterprise_id": args.enterprise_id,
        "factory_id": args.factory_id,
        "zone_id": args.zone_id,
        "camera_id": args.camera_id,
        "confidence": args.confidence,
        "snapshot_key": None,
        "config_version": 1,
    }

    await exchange.publish(
        aio_pika.Message(body=json.dumps(body).encode()),
        routing_key=routing_key,
    )
    print(f"[test] Published {routing_key} -> {body}")
    await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--enterprise-id", required=True)
    parser.add_argument("--factory-id", required=True)
    parser.add_argument("--zone-id", required=True)
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--type", default="helmet_missing",
                         choices=["helmet_missing", "vest_missing", "gloves_missing", "shoes_missing"])
    parser.add_argument("--confidence", type=float, default=0.87)
    asyncio.run(publish(parser.parse_args()))
