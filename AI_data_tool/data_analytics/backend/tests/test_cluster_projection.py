"""Groups of similar rows, as a picture (docs/discovery/PLAN.md, phase 2 #8)."""
import numpy as np
import pandas as pd

from app.services.analysis.segment import PROJECTION_POINTS, segment_dataframe


def blobs(n=900, dims=5, seed=4):
    rng = np.random.default_rng(seed)
    centres = np.array([[0] * dims, [6] * dims, [-6, 6] + [0] * (dims - 2)], dtype=float)
    which = rng.integers(0, 3, n)
    X = centres[which] + rng.normal(0, 0.6, (n, dims))
    return pd.DataFrame(X, columns=[f"c{i}" for i in range(dims)]), which


def test_the_groups_are_placed_in_two_dimensions_and_stay_apart():
    df, _ = blobs()
    meta = segment_dataframe(df, list(df.columns)).to_dict()["meta"]
    proj = meta["projection"]
    assert meta["params"]["k"] == 3 and proj["method"] == "pca"
    assert len(proj["points"]) == 900 and len(proj["centers"]) == 3 and proj["shown"] == proj["of"] == 900
    pts = np.array(proj["points"])
    centres = {int(c[2]): np.array(c[:2]) for c in proj["centers"]}
    # Each point is nearest to the centre of its OWN group in the picture too.
    nearest = [min(centres, key=lambda k: np.linalg.norm(p[:2] - centres[k])) for p in pts]
    assert np.mean(np.array(nearest) == pts[:, 2]) > 0.97


def test_each_axis_says_what_it_is_made_of():
    df, _ = blobs()
    axes = segment_dataframe(df, list(df.columns)).to_dict()["meta"]["projection"]["axes"]
    assert len(axes) == 2 and axes[0]["share"] >= axes[1]["share"] > 0
    assert sum(a["share"] for a in axes) <= 1.0 + 1e-9
    assert all(v["name"] in df.columns for a in axes for v in a["variables"]) and len(axes[0]["variables"]) == 3


def test_a_large_table_is_drawn_from_a_sample_and_says_so():
    df, _ = blobs(n=4000)
    proj = segment_dataframe(df, list(df.columns)).to_dict()["meta"]["projection"]
    assert proj["shown"] == PROJECTION_POINTS == len(proj["points"]) and proj["of"] == 4000


def test_the_same_data_gives_the_same_picture():
    df, _ = blobs()
    a = segment_dataframe(df, list(df.columns)).to_dict()["meta"]["projection"]
    b = segment_dataframe(df, list(df.columns)).to_dict()["meta"]["projection"]
    assert a == b
