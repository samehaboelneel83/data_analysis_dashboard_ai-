"""Build-time-only weight download. Runs exclusively inside the Dockerfile
RUN layer -- see the Dockerfile's comment block on host-disk discipline.
Never invoke this on the host; it writes to /model inside the image, not
to any host cache/temp path.

Downloads both the fp32 ONNX export and the int8 quantized export so the
rank-stability check (rank_stability.py) can compare them inside the
built image before the server commits to one at runtime.
"""
from huggingface_hub import snapshot_download

snapshot_download(
    "Xenova/paraphrase-multilingual-MiniLM-L12-v2",
    local_dir="/model",
    allow_patterns=[
        "onnx/model.onnx",
        "onnx/model_int8.onnx",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "config.json",
    ],
)
print("download_model: done")
