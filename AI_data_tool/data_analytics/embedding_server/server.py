"""Self-hosted embeddings server -- Task M1 of
docs/superpowers/plans/2026-08-30-embeddings-service.md.

CLIENT CONTRACT (read from backend/app/services/retrieval.py
`_request_embeddings`, quoted here so the two sides never drift silently):

    base = settings.embedding_base_url.rstrip("/")
    resp = httpx.post(
        f"{base}/embeddings",
        json={"model": settings.embedding_model, "input": texts},
        timeout=_EMBED_REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = sorted(payload["data"], key=lambda row: row["index"])
    vectors = [row["embedding"] for row in data]
    if len(vectors) != len(texts):
        raise ValueError(...)

So: the client POSTs `{"model": ..., "input": [str, ...]}` to
`{embedding_base_url}/embeddings` (compose sets `EMBEDDING_BASE_URL` to
this service's `/v1`, giving the OpenAI-conventional `/v1/embeddings`
route) and reads `payload["data"]`, a list of `{"index": int, "embedding":
[float, ...]}` rows, in any order (it re-sorts by "index"). Everything
else in the OpenAI shape (object/model/usage fields) is decoration the
client never reads -- included below only because it's free and keeps
the route honestly "OpenAI-compatible" for any other future client.

No torch, no sentence-transformers: ONNX Runtime + tokenizers + numpy
only (see requirements.txt and the Dockerfile for why). Mean-pooling and
L2-normalization are implemented by hand per the model card, matching
what sentence-transformers' pooling layer does internally.
"""
from __future__ import annotations

import logging
import os

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from tokenizers import Tokenizer

logger = logging.getLogger("embedding_server")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Config -- fixed in-image paths the Dockerfile downloads weights into, and
# the model identity the server reports on /health and echoes in responses.
# ---------------------------------------------------------------------------
MODEL_DIR = os.environ.get("MODEL_DIR", "/model")
ONNX_FILENAME = os.environ.get("ONNX_FILENAME", "model.onnx")  # see Dockerfile
                                                                # comment for the
                                                                # fp32-vs-int8 call
MODEL_NAME = os.environ.get(
    "EMBEDDING_MODEL_NAME",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
EMBEDDING_DIM = 384
MAX_SEQ_LENGTH = 256

#: The plan's "reject >256 inputs per call with 413" -- retrieval.py batches
#: documents plus one query per rank() call; the live catalog is small, but
#: this caps a runaway/misbehaving caller rather than trusting it.
MAX_BATCH_SIZE = 256

app = FastAPI(title="embedding_server")

_tokenizer: Tokenizer | None = None
_session: ort.InferenceSession | None = None


@app.on_event("startup")
def _load_model() -> None:
    global _tokenizer, _session
    tokenizer_path = os.path.join(MODEL_DIR, "tokenizer.json")
    onnx_path = os.path.join(MODEL_DIR, "onnx", ONNX_FILENAME)

    _tokenizer = Tokenizer.from_file(tokenizer_path)
    _tokenizer.enable_truncation(max_length=MAX_SEQ_LENGTH)
    _tokenizer.enable_padding(pad_id=0, pad_token="<pad>")

    # Intra-op threads capped: this is a CPU-only container sharing a host
    # with everything else in compose: an unbounded thread pool would let
    # one embedding batch contend for every core.
    so = ort.SessionOptions()
    so.intra_op_num_threads = int(os.environ.get("ORT_INTRA_OP_THREADS", "2"))
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    _session = ort.InferenceSession(
        onnx_path, sess_options=so, providers=["CPUExecutionProvider"]
    )
    logger.info(
        "embedding_server: loaded %s (dim=%d) from %s",
        ONNX_FILENAME,
        EMBEDDING_DIM,
        onnx_path,
    )


def _mean_pool_l2norm(
    last_hidden_state: np.ndarray, attention_mask: np.ndarray
) -> np.ndarray:
    """Mean-pool token embeddings over the attention mask, then L2-normalize
    each row -- the model card's pooling recipe (sentence-transformers'
    `Pooling` + `Normalize` modules), reimplemented in numpy since this
    image carries neither library."""
    mask = attention_mask[:, :, None].astype(np.float32)  # (B, T, 1)
    summed = (last_hidden_state * mask).sum(axis=1)  # (B, H)
    counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)  # (B, 1)
    pooled = summed / counts
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    norms = np.clip(norms, a_min=1e-12, a_max=None)
    return pooled / norms


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Tokenize -> ONNX forward -> mean-pool -> L2-normalize -> plain
    python floats, in input order. Raises if the model/tokenizer aren't
    loaded (startup failed) so the caller gets a 500, not a crash."""
    if _tokenizer is None or _session is None:
        raise RuntimeError("model not loaded")

    encodings = _tokenizer.encode_batch(texts)
    input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)

    input_names = {i.name for i in _session.get_inputs()}
    onnx_inputs = {"input_ids": input_ids, "attention_mask": attention_mask}
    if "token_type_ids" in input_names:
        onnx_inputs["token_type_ids"] = np.zeros_like(input_ids)

    outputs = _session.run(None, onnx_inputs)
    last_hidden_state = outputs[0]  # (B, T, H) -- first output per model card
    pooled = _mean_pool_l2norm(last_hidden_state, attention_mask)
    return pooled.astype(np.float64).tolist()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok" if _session is not None else "loading",
        "model": MODEL_NAME,
        "dim": EMBEDDING_DIM,
        "onnx_file": ONNX_FILENAME,
    }


@app.post("/v1/embeddings")
async def create_embeddings(request: Request) -> JSONResponse:
    body = await request.json()
    raw_input = body.get("input")
    if raw_input is None:
        raise HTTPException(status_code=422, detail="'input' is required")
    texts = [raw_input] if isinstance(raw_input, str) else list(raw_input)
    if not texts:
        raise HTTPException(status_code=422, detail="'input' must be non-empty")
    if len(texts) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"batch of {len(texts)} exceeds max {MAX_BATCH_SIZE} inputs",
        )

    try:
        vectors = embed_texts(texts)
    except Exception:
        logger.exception("embedding_server: inference failed")
        raise HTTPException(status_code=500, detail="embedding inference failed")

    data = [
        {"object": "embedding", "index": i, "embedding": vec}
        for i, vec in enumerate(vectors)
    ]
    return JSONResponse(
        {
            "object": "list",
            "data": data,
            "model": body.get("model", MODEL_NAME),
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        }
    )
