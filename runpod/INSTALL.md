# RunPod install — Qwen3-VL vLLM (port 8000) + DocLayout-YOLO (port 8080)

One A40 pod serves both endpoints. Prereqs: pod shell open, `VLLM_KEY` and
`YOLO_KEY` already set as pod env vars (values live in the pod env only —
never in this repo). 502 from the proxy before the servers start is normal.

> Token semantics: `VLLM_KEY` becomes the vLLM OpenAI-compatible `--api-key`;
> `YOLO_KEY` is the Bearer token the YOLO wrapper checks. The orchestrator
> passes the same values as `SLIDEGEN_VLM_TOKEN` / `SLIDEGEN_YOLO_TOKEN`.

## Copy-paste block (run in the pod shell)

```bash
set -e

# 0) deps — vLLM (Qwen3-VL needs >= 0.11), YOLO wrapper stack
pip install --upgrade pip
pip install "vllm>=0.11.0" doclayout-yolo huggingface_hub fastapi "uvicorn[standard]" httpx pillow

# 1) vLLM — Qwen3-VL-8B-Instruct on :8000 (0.6 GPU util leaves headroom for YOLO)
mkdir -p /workspace/logs
nohup vllm serve Qwen/Qwen3-VL-8B-Instruct \
  --host 0.0.0.0 --port 8000 \
  --api-key "$VLLM_KEY" \
  --gpu-memory-utilization 0.6 \
  > /workspace/logs/vllm.log 2>&1 &

# 2) YOLO wrapper — app.py from this repo on :8080
cd /workspace
git clone https://github.com/JK42JJ/insighta-slidegen.git || (cd insighta-slidegen && git pull)
cd insighta-slidegen/runpod/yolo-service
nohup uvicorn app:app --host 0.0.0.0 --port 8080 \
  > /workspace/logs/yolo.log 2>&1 &

# 3) wait for vLLM model load (first run downloads weights — minutes), then health-check both
sleep 5
echo "--- vLLM health (repeat until model list appears) ---"
curl -s http://localhost:8000/v1/models -H "Authorization: Bearer $VLLM_KEY" | head -c 400; echo
echo "--- YOLO health (first call downloads weights once) ---"
curl -s http://localhost:8080/health -H "Authorization: Bearer $YOLO_KEY"; echo
```

## Health criteria (before declaring the pod ready)

- `:8000/v1/models` returns a JSON model list containing `Qwen/Qwen3-VL-8B-Instruct`
  (watch `/workspace/logs/vllm.log` until "Application startup complete").
- `:8080/health` returns `{"status":"ok","model_version":"doclayout-yolo-docstructbench-imgsz1024"}`.
- Optional smoke: POST `/detect` with any presigned image URL returns a `boxes` array
  (over-detection at conf 0.15 is expected — recall first, §3.4).

## Notes

- Wrapper contract: `mac-mini/slidegen-service/model_clients.py` §3
  (`POST /detect {image_url, conf_threshold, max_boxes}` → px-bbox boxes).
- The pod never receives AWS credentials — it fetches frames via presigned
  GET urls issued by the backend only (§4).
- Restart after a pod reboot: re-run steps 1–3 (deps persist in /workspace
  only if the venv lives there; on a fresh container re-run step 0 too).
