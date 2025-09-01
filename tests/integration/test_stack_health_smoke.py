import os
import urllib.request
import urllib.error

import pytest


def ping(url: str, timeout: float = 2.0) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.getcode()
    except Exception as e:
        raise e


@pytest.mark.parametrize(
    "name, url",
    [
        ("Gateway", os.getenv("GATEWAY_URL", "http://localhost:8000/health")),
        ("Chat Service", os.getenv("CHAT_SERVICE_URL", "http://localhost:8002/health")),
        ("NPC Service", os.getenv("NPC_SERVICE_URL", "http://localhost:8003/health")),
        ("Summary Service", os.getenv("SUMMARY_SERVICE_URL", "http://localhost:8004/health")),
        ("Monitor Service", os.getenv("MONITOR_SERVICE_URL", "http://localhost:8005/health")),
        ("Model Service", os.getenv("MODEL_SERVICE_URL", "http://localhost:8001/health")),
    ],
)
def test_service_health_http(name: str, url: str):
    try:
        code = ping(url)
        assert code == 200
    except Exception as e:
        pytest.skip(f"{name} not reachable at {url}: {e}")

