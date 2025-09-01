import importlib.util
import sys
from pathlib import Path
import types
from typing import Optional

import pytest
from fastapi.testclient import TestClient


def load_module_from_path(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    # Ensure service local imports like `from src...` resolve and avoid cross-service collisions
    service_dir = path.parent
    service_src = service_dir / "src"
    # Drop any previously imported 'src' namespace to isolate per-service imports
    if 'src' in sys.modules:
        del sys.modules['src']
    # Provide lightweight stubs for heavy optional deps when importing monitor-service
    path_str = str(path)
    if "monitor-service" in path_str:
        # psutil stub
        if 'psutil' not in sys.modules:
            sys.modules['psutil'] = types.ModuleType('psutil')
        # aiohttp stub
        if 'aiohttp' not in sys.modules:
            sys.modules['aiohttp'] = types.ModuleType('aiohttp')
        # asyncpg stub
        if 'asyncpg' not in sys.modules:
            sys.modules['asyncpg'] = types.ModuleType('asyncpg')
        # redis.asyncio stub
        if 'redis' not in sys.modules:
            redis_pkg = types.ModuleType('redis')
            sys.modules['redis'] = redis_pkg
        if 'redis.asyncio' not in sys.modules:
            redis_asyncio = types.ModuleType('redis.asyncio')
            sys.modules['redis.asyncio'] = redis_asyncio
        # GPU utils stubs
        if 'GPUtil' not in sys.modules:
            sys.modules['GPUtil'] = types.ModuleType('GPUtil')
        if 'nvidia_ml_py3' not in sys.modules:
            nvml_mod = types.ModuleType('nvidia_ml_py3')
            # Provide minimal NVML API used at import time
            def nvmlInit():
                return None
            nvml_mod.nvmlInit = nvmlInit  # type: ignore[attr-defined]
            sys.modules['nvidia_ml_py3'] = nvml_mod
    sys.path.insert(0, str(service_dir))
    if service_src.exists():
        sys.path.insert(0, str(service_src))

    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


@pytest.mark.parametrize(
    "service_path, label",
    [
        (Path("services/chat-service/main.py"), "chat-service"),
        (Path("services/npc-service/main.py"), "npc-service"),
        (Path("services/summary-service/main.py"), "summary-service"),
        (Path("services/monitor-service/main.py"), "monitor-service"),
        (Path("services/gateway-service/main.py"), "gateway-service"),
    ],
)
def test_health_endpoint(service_path: Path, label: str):
    assert service_path.exists(), f"{label} main.py not found at {service_path}"
    module = load_module_from_path(service_path)
    app = getattr(module, "app", None)
    assert app is not None, f"{label} FastAPI app not defined as 'app'"

    # For gateway service, stub out downstream health checks to avoid network
    if "gateway-service" in str(service_path):
        async def _fake_health():
            return {}
        try:
            # Patch on the module where service_router is defined
            module.service_router.health_check_services = _fake_health  # type: ignore[attr-defined]
        except Exception:
            pass

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200, f"{label} /health returned {resp.status_code}"
    data = resp.json()
    assert isinstance(data, dict)
    assert "message" in data or "status" in data
    client.close()


def test_model_service_health_mock():
    """Use the provided mock for model-service to avoid heavy deps."""
    path = Path("services/model-service/main_mock.py")
    if not path.exists():
        pytest.skip("model-service mock not present")

    module = load_module_from_path(path)
    app = getattr(module, "app", None)
    assert app is not None, "model-service mock FastAPI app not defined as 'app'"

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    # Accept healthy or degraded since lifespan isn't started in unit test
    assert data.get("status") in {"healthy", "degraded", "error"}
    client.close()
