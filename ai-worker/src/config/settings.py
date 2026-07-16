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
    METRICS_PORT: int = 8001

    # Option B (no local fine-tuned model yet): call a community-trained PPE
    # model hosted on Roboflow for helmet/vest/gloves/shoes item detection,
    # combined with the local COCO fallback's person boxes via spatial
    # overlap (see detector.py _remote_violations_for_person). Only used
    # when YOLO_MODEL_PATH doesn't exist AND this key is set — leave empty
    # to keep the plain demo-mode rotation fallback.
    ROBOFLOW_API_KEY: str = ""
    ROBOFLOW_MODEL_ID: str = "ppe-detection-yolov11-42krk/1"
    ROBOFLOW_API_URL: str = "https://detect.roboflow.com"
    ROBOFLOW_CONFIDENCE: float = 0.4
    ROBOFLOW_TIMEOUT_SECONDS: float = 5.0

    # Must match backend's WORKER_API_KEY — authenticates service-to-service calls
    # (heartbeat, camera assignment fetch) that happen before any user is logged in.
    WORKER_API_KEY: str = "dev-worker-key-change-me"
    ENTERPRISE_ID: str = ""

    FRAME_SAMPLE_FPS: int = 2
    REQUIRED_CONSECUTIVE_FRAMES: int = 3
    SNAPSHOT_CONFIDENCE_THRESHOLD: float = 0.60
    LOW_CONFIDENCE_FLOOR: float = 0.40

    # Mandatory camera installation spec (AI_MASTER_CONTEXT Section 18) —
    # platform-wide minimums, not per-camera: "Minimum 1080p @ 15 FPS".
    # A stream below either triggers a CAMERA_SPEC_MISMATCH alert so a
    # degraded feed (bad NVR transcode, network throttling, wrong lens)
    # gets caught even though it never actually disconnects.
    MIN_EXPECTED_FPS: float = 15.0
    MIN_EXPECTED_WIDTH: int = 1920
    MIN_EXPECTED_HEIGHT: int = 1080


settings = WorkerSettings()
