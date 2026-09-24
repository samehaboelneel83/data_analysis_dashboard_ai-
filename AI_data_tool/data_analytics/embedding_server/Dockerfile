# Self-hosted multilingual embeddings service -- Task M1 of
# docs/superpowers/plans/2026-08-30-embeddings-service.md. See
# ARCHITECTURE.md "The embeddings service -- concrete design" for the
# settled spec (model, no-torch runtime, compose-network-only, host-disk
# discipline).
#
# HOST-DISK DISCIPLINE (binding): the dev host's C: drive was down to
# ~0.6GB free when this was built. ALL model download happens in the RUN
# layer below, writing into the IMAGE at /model -- never to a host
# HuggingFace cache, host temp dir, or the scratchpad. Build from
# PowerShell with `docker build --pull=false ...` so a base-image re-pull
# never touches host disk either (python:3.12-slim lives in Docker's
# WSL2 vhdx, which has its own headroom separate from host C:).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
# --timeout/--retries match backend/Dockerfile: pip's default 15s read timeout
# is routinely exceeded by files.pythonhosted.org on a slow or contended link,
# and one timed-out wheel fails the whole build (and cancels every sibling
# target with it). The retry on line 33 below already exists for the same class
# of transient network flake -- this closes the other half.
RUN pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt

COPY download_model.py .

# Build-time-only weight download (never touches the network again after
# this layer). Repo file listing verified beforehand via
# `huggingface_hub.HfApi().list_repo_files("Xenova/paraphrase-multilingual-MiniLM-L12-v2")`
# run inside a throwaway `docker run --rm python:3.12-slim ...` (not on
# the host): the repo carries onnx/model.onnx (fp32), onnx/model_int8.onnx,
# onnx/model_quantized.onnx, onnx/model_uint8.onnx, tokenizer.json,
# tokenizer_config.json, special_tokens_map.json, config.json, unigram.json.
# Both fp32 and int8 are pulled so rank_stability.py can compare them
# inside the built image before the server commits to one at runtime.
# Retry once on transient HuggingFace/registry flakes.
RUN python download_model.py || (echo "download_model: retrying once after a pause..." && sleep 5 && python download_model.py)

# --- fp32-vs-int8 rank-stability result (Task M1 gate) ---------------------
# Ran `docker run --rm <image> python rank_stability.py` against this
# build: Spearman rank correlation between fp32 and int8 rank order on the
# 10-pair fixture (EN synonym/unrelated, AR synonym/unrelated, EN<->AR
# cross-lingual) was 1.0000 -- exact rank-order match, no swaps. int8 is
# used at runtime (ONNX_FILENAME=model_int8.onnx (the server prefixes onnx/) below); see the PR/
# commit message for the full printed table. If a future re-run of
# rank_stability.py in a rebuilt image shows instability, flip
# ONNX_FILENAME back to "model.onnx" (fp32) -- no code change needed,
# both files are already baked into /model.
COPY server.py smoke.py rank_stability.py .

ENV MODEL_DIR=/model \
    ONNX_FILENAME=model_int8.onnx \
    EMBEDDING_MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
    ORT_INTRA_OP_THREADS=2

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
