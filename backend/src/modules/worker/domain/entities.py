from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class WorkerEntity:
    id: UUID
    enterprise_id: UUID
    worker_id: str          # string identifier from env (e.g. "worker-1")
    status: str             # Online / Offline / Degraded
    hostname: str | None = None
    model_version: str | None = None
    gpu_available: bool = False
    last_heartbeat: datetime | None = None

    @property
    def is_alive(self) -> bool:
        if not self.last_heartbeat:
            return False
        from datetime import timezone
        age = (datetime.now(timezone.utc) - self.last_heartbeat).total_seconds()
        return age < 60  # missed 2+ heartbeats (30s interval) = dead
