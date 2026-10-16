"""Process-bound camera leases; cached authorization never extends a deadline."""
from datetime import datetime, timedelta
import math
import time
from uuid import UUID, uuid4

SESSION_ID = str(uuid4())
STOP_MARGIN_SECONDS = 5


class LeaseExpired(RuntimeError):
    pass


def lease_clock():
    # Linux CLOCK_BOOTTIME advances during suspend; CLOCK_MONOTONIC does not.
    return time.clock_gettime(time.CLOCK_BOOTTIME) if hasattr(time, "CLOCK_BOOTTIME") else time.monotonic()


def bind_assignments(cameras, request_started):
    received = lease_clock()
    for camera in cameras:
        lease = camera["lease"]
        UUID(lease["token"])
        if lease["session_id"] != SESSION_ID or type(lease["generation"]) is not int or lease["generation"] < 1:
            raise ValueError("Invalid camera ownership")
        ttl = lease["ttl_seconds"]
        if type(ttl) not in (int, float) or not math.isfinite(ttl) or not 0 < ttl <= 90:
            raise ValueError("Invalid lease duration")
        server_time = datetime.fromisoformat(lease["server_time"])
        expiry = datetime.fromisoformat(lease["expires_at"])
        if server_time.tzinfo is None or expiry.tzinfo is None or (expiry - server_time).total_seconds() != ttl:
            raise ValueError("Invalid lease window")
        # Charge the entire request (including DB locks and response transit)
        # against the TTL; host clock skew cannot lengthen camera ownership.
        lease["deadline"] = request_started + ttl - STOP_MARGIN_SECONDS
        lease["received_monotonic"] = received
    return cameras


def lease_valid(lease):
    return bool(lease and lease.get("session_id") == SESSION_ID
        and isinstance(lease.get("deadline"), (int, float))
        and math.isfinite(lease["deadline"]) and lease_clock() < lease["deadline"])


def event_ownership(lease):
    if not lease_valid(lease):
        raise LeaseExpired("Camera ownership expired")
    observed = datetime.fromisoformat(lease["server_time"]) + timedelta(
        seconds=max(0, lease_clock() - lease["received_monotonic"]))
    return {"camera_lease": {"token": lease["token"], "generation": lease["generation"],
        "session_id": lease["session_id"], "observed_at": observed.isoformat()}}
