"""Independent retries: an unavailable evidence store never gates event delivery."""
import asyncio
import json

import structlog

from src.health.metrics import edge_delivery_failures, edge_pending, edge_oldest_age, edge_pending_bytes

log = structlog.get_logger()


class EdgeDelivery:
    def __init__(self, journal, send_event, send_evidence):
        self.journal = journal
        self.senders = {"event": send_event, "evidence": send_evidence}
        self.tasks = []

    def start(self):
        self.tasks = [asyncio.create_task(self._run(channel)) for channel in self.senders]

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []

    async def once(self, channel):
        row = await asyncio.to_thread(self.journal.next_due, channel)
        if row is None:
            return False
        try:
            await self.senders[channel](row, json.loads(row["payload"]))
            # If delivery succeeded but this commit fails, replay keeps the ID/key.
            await asyncio.to_thread(self.journal.succeeded, row["event_id"], channel)
        except Exception as error:
            edge_delivery_failures.labels(channel=channel).inc()
            log.warning("edge.delivery_retry", channel=channel, error_type=type(error).__name__)
            await asyncio.to_thread(self.journal.failed, row["event_id"], channel)
        return True

    async def _run(self, channel):
        while True:
            try:
                worked = await self.once(channel)
                stats = await asyncio.to_thread(self.journal.stats)
                edge_pending.labels(channel="event").set(stats["events"])
                edge_pending.labels(channel="evidence").set(stats["evidence"])
                edge_pending_bytes.set(stats["bytes"])
                edge_oldest_age.set(stats["oldest_age"])
                await asyncio.sleep(0.01 if worked else 1)
            except Exception as error:
                edge_delivery_failures.labels(channel=channel).inc()
                log.error("edge.delivery_loop_failed", channel=channel, error_type=type(error).__name__)
                await asyncio.sleep(2)
