from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    BACKEND_API_URL: str = "http://localhost:8000"
    RABBITMQ_URL: str = "amqp://vguser:vgpass@localhost:5672/visionguard"
    REDIS_URL: str = "redis://:redispass@localhost:6379/0"

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_SNAPSHOTS: str = "snapshots"

    WORKER_ID: str = "worker-1"
    USE_GPU: bool = True
    YOLO_MODEL_PATH: str = "models/yolov8s-ppe.pt"

    # Must match backend's WORKER_API_KEY — authenticates service-to-service calls
    # (heartbeat, camera assignment fetch) that happen before any user is logged in.
    WORKER_API_KEY: str = "dev-worker-key-change-me"
    ENTERPRISE_ID: str = ""

    FRAME_SAMPLE_FPS: int = 2
    REQUIRED_CONSECUTIVE_FRAMES: int = 3
    SNAPSHOT_CONFIDENCE_THRESHOLD: float = 0.60
    LOW_CONFIDENCE_FLOOR: float = 0.40


settings = WorkerSettings()
