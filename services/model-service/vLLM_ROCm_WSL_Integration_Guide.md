
# vLLM on WSL + ROCm — Integration & Refactor Guide

**Owner:** Sam Wynn  
**Target GPU:** AMD Radeon **RX 7900 XTX** (RDNA3 / `gfx1100`)  
**Runtime:** **Windows 11 + WSL2 (Ubuntu 22.04/24.04)**, **Docker** containers  
**Serving stack:** **vLLM** (OpenAI-compatible API) in a ROCm-enabled container

> **Important (WSL GPU access):** In WSL, the GPU is exposed as **`/dev/dxg`** (not `/dev/kfd`). You must also mount **`/usr/lib/wsl/lib/libdxcore.so`** and **`/opt/rocm/lib/libhsa-runtime64.so.1`** into your container. See AMD’s WSL instructions for vLLM and PyTorch.  
> References: [AMD ROCm WSL install](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/install/wsl/install-radeon.html), [WSL support matrix](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/compatibility/wsl/wsl_compatibility.html), [vLLM on ROCm/WSL (AMD)](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/advanced/vllm/build-docker-image.html)

---

## 1) Platform Overview

### 1.1 Why vLLM
- vLLM exposes an **OpenAI‑compatible** HTTP API (`/v1/*`), so we can reuse OpenAI SDKs with minimal code changes.  
- AMD provides **vLLM ROCm images** and **WSL-specific launch options** for RDNA3 (RX 7900 series).  
  References: [AMD vLLM Docker build & WSL notes](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/advanced/vllm/build-docker-image.html), [rocm/vllm-dev on Docker Hub](https://hub.docker.com/r/rocm/vllm-dev)

### 1.2 ROCm on WSL Requirements
- **Windows Driver:** AMD **Adrenalin Edition for WSL2** matching your ROCm version.  
- **WSL Distro:** Ubuntu **22.04** or **24.04**.  
- **ROCm:** Install via AMD’s `amdgpu-install --usecase wsl,rocm --no-dkms`.  
- **Support Matrix:** RX 7900 XTX is supported on ROCm 6.4.x for WSL.  
  References: [Install ROCm for WSL](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/install/wsl/install-radeon.html), [WSL compatibility matrix](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/compatibility/wsl/wsl_compatibility.html)

---

## 2) Deployment: Container & Network

### 2.1 `docker-compose.yml`
We run **one vLLM container** that:
- maps `/dev/dxg` and mounts the two WSL/ROCm libraries,  
- uses `./models` on the host to cache model weights,  
- exposes an **OpenAI-style** endpoint at **`http://localhost:8000/v1`**,  
- includes a health check at **`/health`**.

```yaml
a version: "3.8"

services:
  vllm:
    image: rocm/vllm-dev:rocm6.4.2_navi_ubuntu24.04_py3.12_pytorch_2.7_vllm_0.9.2
    container_name: vllm_rocm_container
    network_mode: host
    ipc: host
    shm_size: "16g"
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
    devices:
      - /dev/dxg
    volumes:
      - /usr/lib/wsl/lib/libdxcore.so:/usr/lib/libdxcore.so:ro
      - /opt/rocm/lib/libhsa-runtime64.so.1:/opt/rocm/lib/libhsa-runtime64.so.1:ro
      - ./models:/models
    working_dir: /app/vllm/
    entrypoint: /bin/bash
    command: >
      bash -c "sed -i 's/is_rocm = False/is_rocm = True/g'
      /opt/conda/envs/py_3.12/lib/python3.12/site-packages/vllm/platforms/__init__.py &&
      python -m vllm.entrypoints.openai.api_server
      --model meta-llama/Llama-3.1-8B-Instruct
      --download-dir /models"
    environment:
      - LOGGING_LEVEL=info            # placeholder for app-side logging
      - LOGGING_ENDPOINT=http://localhost:5000/logs
      - OPENAI_API_KEY=local-dev      # not enforced by server unless configured
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 5
```

> **Why `dxg` and library mounts?** WSL’s GPU bridge is DirectX (DX12). The container needs access to `/dev/dxg` plus user‑space shims (`libdxcore.so` and ROCm’s `libhsa-runtime64.so.1`). AMD’s vLLM-on‑WSL guide shows these exact mappings.  
> References: [AMD vLLM WSL config](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/advanced/vllm/build-docker-image.html)

### 2.2 Startup
```bash
mkdir -p models
docker compose up -d
# Health
curl http://localhost:8000/health
# List models
curl http://localhost:8000/v1/models
```

---

## 3) API Surface (OpenAI‑Compatible)

vLLM’s server exposes **OpenAI Chat Completions** endpoints under `/v1`. Use the official OpenAI SDKs and point them to our local base URL.

### 3.1 Base configuration
- **Base URL:** `http://localhost:8000/v1`
- **API Key:** Pass any non-empty string (e.g., `local-dev`) unless we enforce auth.
- **Model name:** Must match the server’s `--model` (e.g., `meta-llama/Llama-3.1-8B-Instruct`).

### 3.2 Python (OpenAI SDK)
```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="local-dev")

resp = client.chat.completions.create(
    model="meta-llama/Llama-3.1-8B-Instruct",
    messages=[{"role":"user","content":"Say hello from vLLM ROCm on WSL!"}],
    temperature=0.6,
    top_p=0.9,
    max_tokens=256,
)
print(resp.choices[0].message.content)
```

### 3.3 Python Streaming
```python
stream = client.chat.completions.create(
    model="meta-llama/Llama-3.1-8B-Instruct",
    messages=[{"role":"user","content":"Stream a short poem about Austin clouds."}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta
    if delta and delta.content:
        print(delta.content, end="", flush=True)
```

### 3.4 TypeScript (OpenAI SDK)
```ts
import OpenAI from "openai";

const client = new OpenAI({ baseURL: "http://localhost:8000/v1", apiKey: "local-dev" });

const resp = await client.chat.completions.create({
  model: "meta-llama/Llama-3.1-8B-Instruct",
  messages: [{ role: "user", content: "Hello from vLLM ROCm on WSL!" }],
  temperature: 0.6,
  top_p: 0.9,
  max_tokens: 256,
});
console.log(resp.choices[0].message?.content);
```

> References: vLLM OpenAI server entrypoint: `vllm.entrypoints.openai.api_server` (see AMD vLLM doc)  
> [AMD vLLM Docker build & WSL notes](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/advanced/vllm/build-docker-image.html)

---

## 4) Model Management

- The compose file uses `--download-dir /models` (host-mapped to `./models`). First run pulls from **Hugging Face**.  
- If the model requires auth, set `HUGGING_FACE_HUB_TOKEN` in container env or export it in WSL before `docker compose up`.  
- To switch models, change the `--model` flag in compose and restart.  
  References: [AMD vLLM Docker image notes](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/advanced/vllm/build-docker-image.html), [rocm/vllm-dev](https://hub.docker.com/r/rocm/vllm-dev)

---

## 5) Refactor Checklist

1. **Abstract the LLM client** behind a small adapter (e.g., `llm_client.py` or `llmClient.ts`).
2. Replace legacy llama.cpp bindings or custom HTTP with **OpenAI Chat Completions** calls.
3. Ensure **streaming** handling in the UI/CLI is propagated correctly.
4. Map sampling params (temperature, top_p, max_tokens, stop, etc.).
5. **System prompts & tools:** Use the first `system` message. If using function/tool calling, validate parity and update schemas.
6. Add **timeouts and retries** for long contexts or batch loads.
7. Add **observability hooks** (prompt hash, params, tokens, latency, status) for later wiring to Cosmos DB/Event Grid.

---

## 6) Testing & Validation

### 6.1 Smoke tests
- Health: `GET http://localhost:8000/health` ⇒ `200 OK`
- Models: `GET http://localhost:8000/v1/models`
- Basic completion: run Python/TS snippets above.

### 6.2 Functional tests
- End‑to‑end **streaming** in your UI.
- **Prompt formatting** (system + user + tools) renders expected outputs.
- **Token budgets**: RX 7900 XTX has 24 GB VRAM. Plan context length and batch sizes accordingly; use quantized models for larger contexts.

### 6.3 Performance sanity
- Measure latency/throughput at realistic batch sizes.  
- Keep `shm_size` generous (we use `16g`), ensure system RAM headroom to avoid swapping.

---

## 7) Logging, Metrics, and Audit (placeholders)

- Compose exposes `LOGGING_ENDPOINT` / `LOGGING_LEVEL` for your app.  
- Capture per‑request: timestamp, user/session, model id, sampling params, prompt hash, token counts (prompt/response), latency, status/error.  
- We will later wire this into **Azure Cosmos DB** + **Event Grid** (sidecar or middleware).

---

## 8) WSL‑Specific Pitfalls & Fixes

- **Do not use `/dev/kfd`** on WSL; use **`/dev/dxg`** and mount `libdxcore.so` + `libhsa-runtime64.so.1`.  
- **Driver/Distro alignment:** Ensure Windows **Adrenalin for WSL2** version and WSL Ubuntu version match the ROCm WSL matrix.  
- **First‑run downloads:** Models are large—persist `./models` and consider pre‑seeding.  
  References: [WSL compatibility matrix](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/compatibility/wsl/wsl_compatibility.html), [AMD vLLM WSL config](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/advanced/vllm/build-docker-image.html)

---

## 9) Local Developer Quickstart

```bash
# 1) Ensure ROCm user-space is installed in WSL (Ubuntu):
#    sudo amdgpu-install -y --usecase=wsl,rocm --no-dkms

# 2) (Optional) Pull the image
docker pull rocm/vllm-dev:rocm6.4.2_navi_ubuntu24.04_py3.12_pytorch_2.7_vllm_0.9.2

# 3) Start the service
mkdir -p models
docker compose up -d

# 4) Health
curl http://localhost:8000/health

# 5) Example request (OpenAI Chat Completions)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local-dev" \
  -d '{
        "model": "meta-llama/Llama-3.1-8B-Instruct",
        "messages": [{"role":"user", "content":"Quick sanity test."}],
        "max_tokens": 64
      }'
```

References: [Install ROCm for WSL](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/install/wsl/install-radeon.html), [vLLM WSL adjustments](https://rocm.docs.amd.com/projects/radeon/en/latest/docs/advanced/vllm/build-docker-image.html), [rocm/vllm-dev](https://hub.docker.com/r/rocm/vllm-dev)

---

## 10) References (Primary)
- AMD — **Install Radeon software for WSL with ROCm**:  
  https://rocm.docs.amd.com/projects/radeon/en/latest/docs/install/wsl/install-radeon.html
- AMD — **WSL support matrix** (OS, driver, GPU list including RX 7900 XTX):  
  https://rocm.docs.amd.com/projects/radeon/en/latest/docs/compatibility/wsl/wsl_compatibility.html
- AMD — **vLLM Docker image for Llama2/Llama3 (WSL configs included)**:  
  https://rocm.docs.amd.com/projects/radeon/en/latest/docs/advanced/vllm/build-docker-image.html
- Docker Hub — **rocm/vllm-dev**:  
  https://hub.docker.com/r/rocm/vllm-dev
- AMD — **Install PyTorch for ROCm on WSL (shows WSL `dxg` + lib mounts)**:  
  https://rocm.docs.amd.com/projects/radeon/en/latest/docs/install/wsl/install-pytorch.html

---

## 11) Acceptance Criteria

1. App targets **OpenAI API** at `http://localhost:8000/v1`.  
2. **Streaming** works end‑to‑end.  
3. **Model switching** configurable without code changes.  
4. **Telemetry** (latency, tokens, status) emitted to logging hook.  
5. All **smoke tests** pass locally on RX 7900 XTX with WSL + vLLM.

