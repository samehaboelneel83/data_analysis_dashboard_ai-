"""An analysis refuses in the reader's language.

Each refusal is a keyed sentence: the English text is unchanged (it is what
logs, tests and the model read), and the key with its pieces travels beside it
so the browser can say it from its own catalogue.
"""
import re
from pathlib import Path

import pandas as pd
import pytest

from app.core.said_errors import SaidHTTPException, refused
from app.services.analysis import goal_seek as gs
from app.services.analysis import inferential
from app.services.readback import Said


def test_a_refusal_keeps_its_english_and_carries_its_key():
    with pytest.raises(gs.GoalSeekError) as e:
        gs.goal_seek(pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]}), "x", "nope", 5)
    assert str(e.value) == "Column 'nope' not found"
    said = e.value.args[0]
    assert isinstance(said, Said) and said.as_i18n()["vars"] == {"a": "nope"}


def test_the_http_form_carries_both():
    try:
        inferential.correlation_test(pd.DataFrame({"a": [1.0] * 40, "b": list(range(40))}), "a", "b")
    except ValueError as e:
        out = refused(400, e)
    assert isinstance(out, SaidHTTPException)
    assert out.detail == "One of the columns is constant, so no correlation is defined"
    assert out.detail_i18n["key"].startswith("no.")


def test_an_ordinary_error_is_left_as_it_was():
    out = refused(400, ValueError("plain"))
    assert not isinstance(out, SaidHTTPException) and out.detail == "plain"


def _catalogue(name: str) -> dict:
    path = Path("/frontend/src/i18n") / name
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / "frontend/src/i18n" / name
    if not path.exists():
        pytest.skip("the frontend catalogue is not on this machine")
    return dict(re.findall(r"^\s*'(rb\.no\.[^']+)':\s*(.+),\s*$", path.read_text(encoding="utf-8"), re.M))


def test_every_refusal_key_is_in_both_catalogues():
    used = set()
    root = Path(__file__).resolve().parents[1] / "app/services"
    for path in list((root / "analysis").glob("*.py")) + [root / "forecast_goal.py"]:
        used |= set(re.findall(r'_s\("(no\.[a-z_]+\.\d+)"', path.read_text(encoding="utf-8")))
    assert len(used) > 100
    for name in ("en.ts", "ar.ts"):
        have = {k[3:] for k in _catalogue(name)}
        assert used <= have, sorted(used - have)[:5]


def test_a_finding_detail_and_the_summary_carry_their_keys():
    import numpy as np
    from app.services.insights import generate_insights
    rng = np.random.default_rng(3)
    n = 600
    group = rng.choice(["a", "b", "c", "d"], n, p=[0.7, 0.1, 0.1, 0.1])
    df = pd.DataFrame({"group": group,
                       "amount": np.where(group == "a", 900, 100) + rng.normal(0, 20, n)})
    out = generate_insights(df, {"group": "categorical", "amount": "numeric"})
    keyed = [f for f in out["findings"] if f.get("detail_i18n")]
    assert keyed, [f["detail"] for f in out["findings"]]
    for f in keyed:
        assert isinstance(f["detail"], str) and f["detail_i18n"]["key"].startswith(("ins.d.", "seq."))
    assert out["narrative_i18n"]["key"].startswith("ins.n.")
    assert out["narrative"].startswith("Across 600 rows")


def test_a_job_error_keeps_its_key_for_later():
    from app.services import jobs
    from app.services.readback import _s
    keyed = jobs.JobError(_s("job.datasetGone", "The dataset is gone, or no longer readable by you."), code="not_found")
    assert str(keyed) == "The dataset is gone, or no longer readable by you."
    assert jobs._failed(keyed.said) == {"stage": "failed", "error_i18n": {"key": "job.datasetGone", "vars": {}}}
    plain = jobs.JobError("something else")
    assert plain.said is None and jobs._failed(plain.said) == {"stage": "failed"}


def test_stored_status_lines_are_the_ones_the_browser_knows():
    """The browser words these lines from their stored English
    (frontend/src/lib/storedStatus.ts). Change one here and its pattern there
    must change with it -- this is the reminder."""
    root = Path(__file__).resolve().parents[1] / "app/services"
    alerts = (root / "alerts.py").read_text(encoding="utf-8")
    delivery = (root / "delivery.py").read_text(encoding="utf-8")
    for line in ('"clear"', '"still firing (no re-send)"', 'f"fired, emailed {len(recipients)}"',
                 '"posted to webhook"', '"fired, no valid recipients"', 'f"evaluation failed: {e}"',
                 '"disabled: dataset or creator no longer exists"'):
        assert line in alerts, line
    for line in ('"no valid recipients"', '"nothing to send"', 'f"build failed: {e}"', 'f"emailed {len(to)}"',
                 '"no change since the last delivery -- nothing sent"',
                 '"disabled: report or creator no longer exists"'):
        assert line in delivery, line
