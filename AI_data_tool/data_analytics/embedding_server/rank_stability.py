"""fp32-vs-int8 rank-stability check (Task M1's gate for choosing the int8
quantized ONNX export): 10 text pairs, including Arabic and Arabic<->English
cross-lingual pairs, each expected at a different similarity tier. Cosine
similarity is computed for every pair under both the fp32 (`model.onnx`) and
int8 (`model_int8.onnx`) exports; if the two models agree on the *rank
order* of the 10 pairs (which pair is most similar, least similar, etc.),
int8 is safe to ship -- otherwise the server falls back to fp32 (see the
Dockerfile comment recording the actual result of this run).

Run inside the built image: `docker run --rm <image> python rank_stability.py`.
"""
from __future__ import annotations

import numpy as np
from tokenizers import Tokenizer
import onnxruntime as ort

MODEL_DIR = "/model"
TOKENIZER_PATH = f"{MODEL_DIR}/tokenizer.json"

# 10 pairs spanning: English synonym, Arabic synonym, English/Arabic
# unrelated, and cross-lingual (Arabic<->English) same-concept pairs --
# expected to span the similarity range from high to low.
PAIRS = [
    ("revenue", "sales"),                                  # EN synonym (high)
    ("customer", "client"),                                # EN synonym (high)
    ("total amount due", "invoice balance"),                # EN near-synonym (med-high)
    ("الإيرادات", "المبيعات"),                              # AR synonym: revenue/sales (high)
    ("العميل", "الزبون"),                                   # AR synonym: customer (high)
    ("revenue", "الإيرادات"),                               # cross-lingual same concept (med-high)
    ("customer", "العميل"),                                 # cross-lingual same concept (med-high)
    ("order", "banana"),                                    # EN unrelated (low)
    ("طلب", "موز"),                                         # AR unrelated: order/banana (low)
    ("weather forecast", "quarterly earnings report"),      # EN unrelated (low)
]


def load_session(onnx_filename: str) -> ort.InferenceSession:
    so = ort.SessionOptions()
    so.intra_op_num_threads = 2
    return ort.InferenceSession(
        f"{MODEL_DIR}/onnx/{onnx_filename}", sess_options=so,
        providers=["CPUExecutionProvider"],
    )


def embed(tokenizer: Tokenizer, session: ort.InferenceSession,
          texts: list[str]) -> np.ndarray:
    encodings = tokenizer.encode_batch(texts)
    input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
    input_names = {i.name for i in session.get_inputs()}
    onnx_inputs = {"input_ids": input_ids, "attention_mask": attention_mask}
    if "token_type_ids" in input_names:
        onnx_inputs["token_type_ids"] = np.zeros_like(input_ids)
    last_hidden_state = session.run(None, onnx_inputs)[0]
    mask = attention_mask[:, :, None].astype(np.float32)
    pooled = (last_hidden_state * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
    norms = np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
    return pooled / norms


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def spearman(rank_a: list[int], rank_b: list[int]) -> float:
    n = len(rank_a)
    d2 = sum((ra - rb) ** 2 for ra, rb in zip(rank_a, rank_b))
    return 1 - (6 * d2) / (n * (n**2 - 1))


def main() -> None:
    tokenizer = Tokenizer.from_file(TOKENIZER_PATH)
    tokenizer.enable_truncation(max_length=256)
    tokenizer.enable_padding(pad_id=0, pad_token="<pad>")

    fp32 = load_session("model.onnx")
    int8 = load_session("model_int8.onnx")

    flat = [t for pair in PAIRS for t in pair]

    fp32_vecs = embed(tokenizer, fp32, flat)
    int8_vecs = embed(tokenizer, int8, flat)

    fp32_sims = [cosine(fp32_vecs[2 * i], fp32_vecs[2 * i + 1]) for i in range(len(PAIRS))]
    int8_sims = [cosine(int8_vecs[2 * i], int8_vecs[2 * i + 1]) for i in range(len(PAIRS))]

    # Rank: 0 = most similar pair, len-1 = least similar.
    fp32_order = sorted(range(len(PAIRS)), key=lambda i: -fp32_sims[i])
    int8_order = sorted(range(len(PAIRS)), key=lambda i: -int8_sims[i])
    fp32_rank = [fp32_order.index(i) for i in range(len(PAIRS))]
    int8_rank = [int8_order.index(i) for i in range(len(PAIRS))]

    print(f"{'pair':45s} {'fp32 sim':>10s} {'int8 sim':>10s} {'fp32#':>6s} {'int8#':>6s}")
    for i, (a, b) in enumerate(PAIRS):
        label = f"{a!r} / {b!r}"
        print(f"{label:45.45s} {fp32_sims[i]:10.4f} {int8_sims[i]:10.4f} "
              f"{fp32_rank[i]:6d} {int8_rank[i]:6d}")

    rho = spearman(fp32_rank, int8_rank)
    exact_match = fp32_order == int8_order
    print()
    print(f"Spearman rank correlation (fp32 vs int8): {rho:.4f}")
    print(f"Exact rank order match: {exact_match}")
    print(f"fp32 order (best->worst): {[PAIRS[i] for i in fp32_order]}")
    print(f"int8 order (best->worst): {[PAIRS[i] for i in int8_order]}")

    # Threshold: int8 is acceptable if rank order is (near-)identical.
    stable = rho >= 0.9
    print()
    print("RANK-STABLE: INT8 ACCEPTABLE" if stable else "RANK-UNSTABLE: FALL BACK TO FP32")


if __name__ == "__main__":
    main()
