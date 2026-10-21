"""Native child deadline/reaping without opening any camera."""
import asyncio
import sys

import pytest

from src.modules.camera.application import probe


async def test_stuck_native_probe_is_killed_and_reaped(monkeypatch):
    original = asyncio.create_subprocess_exec
    children = []
    async def stalled(*args, **kwargs):
        assert 'private-password' not in ' '.join(args)
        child = await original(sys.executable, '-c', 'import time; time.sleep(60)', **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(probe.asyncio, 'create_subprocess_exec', stalled)
    monkeypatch.setattr(probe, 'PROBE_SECONDS', 0.1)
    result = await probe.probe_url('rtsp://user:private-password@camera.example.invalid/feed')
    assert not result['reachable'] and children[0].returncode is not None
    assert 'private-password' not in str(result)


async def test_probe_success_and_capacity_limit(monkeypatch):
    original = asyncio.create_subprocess_exec
    async def success(*args, **kwargs):
        return await original(sys.executable, '-c', 'import sys; sys.stdin.buffer.read(); print(\'{"reachable":true}\')', **kwargs)
    monkeypatch.setattr(probe.asyncio, 'create_subprocess_exec', success)
    result = await probe.probe_url('rtsp://camera.example.invalid/feed')
    assert result['reachable']
    limit = probe._LIMITS[asyncio.get_running_loop()]
    await limit.acquire()
    await limit.acquire()
    try:
        with pytest.raises(Exception, match='busy'):
            await probe.probe_url('rtsp://camera.example.invalid/feed')
    finally:
        limit.release()
        limit.release()
