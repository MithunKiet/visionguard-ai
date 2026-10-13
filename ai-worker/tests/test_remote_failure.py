from unittest.mock import Mock

import httpx
import numpy as np
import pytest

from src.pipeline.remote_ppe_client import RoboflowPPEClient


def test_remote_outage_cannot_be_interpreted_as_no_ppe(capsys):
    client = RoboflowPPEClient()
    original = client._client
    original.close()
    client._client = Mock()
    client._client.post.side_effect = httpx.ReadTimeout("https://example.invalid?api_key=private-sentinel")
    with pytest.raises(RuntimeError, match="inference unavailable"):
        client.detect(np.zeros((8, 8, 3), dtype=np.uint8))
    assert "private-sentinel" not in capsys.readouterr().out


def test_valid_empty_prediction_is_distinct_from_malformed_response():
    client = RoboflowPPEClient()
    client._client.close()
    client._client = Mock()
    response = client._client.post.return_value
    response.json.return_value = {"predictions": []}
    assert client.detect(np.zeros((8, 8, 3), dtype=np.uint8)) == []
    response.json.return_value = {"error": "quota exceeded"}
    with pytest.raises(RuntimeError):
        client.detect(np.zeros((8, 8, 3), dtype=np.uint8))
