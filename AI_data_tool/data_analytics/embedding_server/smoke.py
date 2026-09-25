"""Container-level smoke test -- Task M1's acceptance smoke:
    dims 384 / duplicate-input equality / Arabic differs from English /
    L2-norm ~= 1

Run inside the built image: `docker run --rm <image> python smoke.py`.
Imports server.py directly (no HTTP round trip needed) and drives
`_load_model` + `embed_texts` exactly as the FastAPI startup hook does.
"""
import sys

import numpy as np

import server

server._load_model()

texts = ["hello", "مرحبا بالعالم", "hello"]
vectors = server.embed_texts(texts)

ok = True


def check(name: str, cond: bool) -> None:
    global ok
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}")
    if not cond:
        ok = False


arr = np.array(vectors)

check("dims == 384 for every vector", all(len(v) == 384 for v in vectors))
check("duplicate input ('hello' == 'hello') -> identical vectors",
      np.allclose(arr[0], arr[2], atol=1e-6))
check("Arabic vector differs from English vector",
      not np.allclose(arr[0], arr[1], atol=1e-3))

norms = np.linalg.norm(arr, axis=1)
print(f"    L2 norms: {norms.tolist()}")
check("L2-norm ~= 1 for every vector", np.allclose(norms, 1.0, atol=1e-3))

print()
if ok:
    print("SMOKE: ALL CHECKS PASSED")
    sys.exit(0)
else:
    print("SMOKE: FAILURES ABOVE")
    sys.exit(1)
