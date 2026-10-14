"""A decision recognised by its shape and written down, never solved
(docs/discovery/PLAN.md §D2, phase 5)."""
import numpy as np
import pandas as pd
import pytest

from app.services.discovery import decision, engine
from app.services.discovery import profile as store


def options(n=40, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"item": [f"x{i:03d}" for i in range(n)], "gain": rng.uniform(10, 90, n).round(1),
                         "cost": rng.uniform(5, 40, n).round(1), "kind": rng.choice(["a", "b", "c"], n)})


def grid(a=6, b=5, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame([(f"w{i}", f"t{j}", float(rng.integers(1, 50))) for i in range(a) for j in range(b)],
                        columns=["worker", "task", "hours"])


def found(df, types, meta=None):
    profile = store.compute(df, types)
    return decision.recognise(profile, engine.column_kinds(profile, meta))


OPTION_TYPES = {"item": "categorical", "gain": "numeric", "cost": "numeric", "kind": "categorical"}
GRID_TYPES = {"worker": "categorical", "task": "categorical", "hours": "numeric"}


def test_one_row_per_option_with_two_amounts_is_a_choice():
    [got] = found(options(), OPTION_TYPES)
    assert got["problem"] == "allocation" and got["key"] == "item" and set(got["amounts"]) == {"gain", "cost"}
    assert got["options"] == 40


def test_a_table_of_events_is_not_a_choice():
    df = pd.concat([options()] * 3, ignore_index=True)                 # every item three times: no key
    assert not [f for f in found(df, OPTION_TYPES) if f["problem"] == "allocation"]
    dated = options().assign(day=pd.date_range("2025-01-01", periods=40))     # a dated row happened: not an option
    assert found(dated, {**OPTION_TYPES, "day": "datetime"}) == []
    few = options(3)
    assert found(few, OPTION_TYPES) == []
    one_amount = options().drop(columns=["cost"])
    assert found(one_amount, {k: v for k, v in OPTION_TYPES.items() if k != "cost"}) == []


def test_every_a_against_every_b_is_a_matching_and_a_sparse_table_is_not():
    got = [f for f in found(grid(), GRID_TYPES) if f["problem"] == "assignment"]
    assert got and {got[0]["from"], got[0]["to"]} == {"worker", "task"} and got[0]["numbers"] == ["hours"]
    assert got[0]["fill"] == 1.0
    sparse = grid().sample(8, random_state=0)                          # 8 of 30 pairs
    assert not [f for f in found(sparse, GRID_TYPES) if f["problem"] == "assignment"]


def test_the_specification_says_what_the_person_said_and_nothing_more():
    spec = decision.specify(options(), "allocation", key="item", objective="gain", direction="largest",
                            limited="cost", limit=100, dataset={"id": 7, "name": "things"})
    assert spec["schema"] == "datalytics.decision-problem/1" and spec["solved"] is False
    assert spec["objective"] == {"direction": "maximize", "column": "gain", "aggregate": "sum_over_chosen"}
    assert spec["decisions"] == {"unit": "row", "key": "item", "type": "choose", "domain": [0, 1], "count": 40}
    assert spec["constraints"] == [{"kind": "total_at_most", "column": "cost", "value": 100.0}]
    assert spec["dataset"] == {"id": 7, "name": "things"}
    assert {"code": "fit_alone", "options": 40, "of": 40} in spec["checks"]
    assert "x000" not in str(spec)                                     # a description of the problem: no row of the data


def test_what_is_not_a_decision_is_refused_in_plain_words():
    df = options()
    ok = dict(key="item", objective="gain", direction="largest", limited="cost", limit=100)
    with pytest.raises(decision.DecisionProblemError, match="large or as small"):
        decision.specify(df, "allocation", **{**ok, "direction": "better"})
    with pytest.raises(decision.DecisionProblemError, match="needs a limit"):
        decision.specify(df, "allocation", key="item", objective="gain", direction="largest")
    with pytest.raises(decision.DecisionProblemError, match="same column"):
        decision.specify(df, "allocation", **{**ok, "limited": "gain"})
    with pytest.raises(decision.DecisionProblemError, match="each row must be one option"):
        decision.specify(df, "allocation", **{**ok, "key": "kind"})
    with pytest.raises(decision.DecisionProblemError, match="no option fits"):
        decision.specify(df, "allocation", **{**ok, "limit": 1})
    with pytest.raises(decision.DecisionProblemError, match="holds no numbers"):
        decision.specify(df, "allocation", **{**ok, "objective": "kind"})
    with pytest.raises(decision.DecisionProblemError, match="'allocation', 'assignment' or 'response'"):
        decision.specify(df, "routing", **ok)


def test_a_limit_that_binds_nothing_and_missing_values_are_said():
    df = options()
    df.loc[0, "gain"] = np.nan
    spec = decision.specify(df, "allocation", key="item", objective="gain", direction="largest",
                            limited="cost", limit=10_000, at_most=5)
    codes = {c["code"] for c in spec["checks"]}
    assert {"limit_not_binding", "missing"} <= codes
    assert {"kind": "count_at_most", "value": 5} in spec["constraints"]


def test_a_matching_is_written_down_and_an_impossible_one_refused():
    spec = decision.specify(grid(), "assignment", from_col="worker", to_col="task", objective="hours",
                            direction="smallest", each_from="at_most_one")
    assert spec["decisions"]["from_count"] == 6 and spec["decisions"]["to_count"] == 5
    assert spec["constraints"] == [{"kind": "each_from", "column": "worker", "rule": "at_most_one"},
                                   {"kind": "each_to_at_most", "column": "task", "value": 1}]
    with pytest.raises(decision.DecisionProblemError, match="cannot each be matched"):
        decision.specify(grid(), "assignment", from_col="worker", to_col="task", objective="hours",
                         direction="smallest")                       # 6 workers, 5 tasks, one each
    twice = pd.concat([grid(), grid().head(1)])
    with pytest.raises(decision.DecisionProblemError, match="more than once"):
        decision.specify(twice, "assignment", from_col="worker", to_col="task", objective="hours", direction="smallest",
                         each_from="at_most_one")
    holes = grid().drop(index=[0, 1])
    spec = decision.specify(holes, "assignment", from_col="worker", to_col="task", objective="hours",
                            direction="smallest", each_from="at_most_one")
    assert {"code": "pairs_missing", "pairs": 2, "of": 30} in spec["checks"]


def test_the_engine_offers_it_as_something_to_set_up_and_says_it_does_not_solve():
    profile = store.compute(options(), OPTION_TYPES)
    cards = engine.tier0(profile, None)["cards"]
    card = next(c for c in cards if c["capability"] == "decision_problem")
    assert card["action"]["kind"] == "decision_problem" and card["action"]["problem"] == "allocation"
    assert any("does not solve" in l for l in card["limits"])
    assert card["title_i18n"]["key"] == "card.decide.alloc.t"
    # A table with no such shape is offered nothing of the kind.
    from tests.test_cohort_retention import visits
    plain = store.compute(visits().assign(amount=1.0), {"member": "categorical", "seen": "datetime", "amount": "numeric"})
    assert not [c for c in engine.tier0(plain, None)["cards"] if c["capability"] == "decision_problem"]


# ── over the API: read as the reader ─────────────────────────────────────────
@pytest.fixture
def options_csv(tmp_path):
    options().to_csv(tmp_path / "o.csv", index=False)
    return str(tmp_path / "o.csv")


async def _world(db, org, path, *, deny=None):
    from app.core.security import create_access_token, hash_password
    from app.models.models import ColumnSecurityRule, Dataset, DatasetColumn, Role, User
    ds = Dataset(name="Things", filename=path, org_id=org.id, mode="import", row_count=40)
    db.add(ds)
    await db.flush()
    for c, t in OPTION_TYPES.items():
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    role = Role(org_id=org.id, name="reader", is_org_admin=False)
    db.add(role)
    await db.flush()
    if deny:
        db.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=deny))
    user = User(org_id=org.id, role_id=role.id, email="decider@example.com", password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    ds.created_by = user.id
    await db.commit()
    return ds, {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


SAID = {"problem": "allocation", "key": "item", "objective": "gain", "direction": "largest", "limited": "cost", "limit": 100}


async def test_the_shape_is_listed_and_the_specification_written(client, two_orgs, db_session, options_csv):
    ds, headers = await _world(db_session, two_orgs["a"]["org"], options_csv)
    got = (await client.get(f"/api/v1/datasets/{ds.id}/decision-problems", headers=headers)).json()
    assert [p["problem"] for p in got["problems"]] == ["allocation"] and got["problems"][0]["key"] == "item"
    r = await client.post(f"/api/v1/datasets/{ds.id}/decision-problems/specification", json=SAID, headers=headers)
    assert r.status_code == 200, r.text
    spec = r.json()
    assert spec["schema"] == "datalytics.decision-problem/1" and spec["solved"] is False
    assert spec["dataset"]["id"] == ds.id and spec["dataset"]["name"] == "Things"
    assert spec["constraints"] == [{"kind": "total_at_most", "column": "cost", "value": 100.0}]
    bad = await client.post(f"/api/v1/datasets/{ds.id}/decision-problems/specification",
                            json={**SAID, "limit": 1}, headers=headers)
    assert bad.status_code == 400 and "no option fits" in bad.json()["detail"]


async def test_a_hidden_column_cannot_be_named_and_another_organisation_sees_nothing(
        client, two_orgs, db_session, options_csv, auth_headers):
    ds, headers = await _world(db_session, two_orgs["a"]["org"], options_csv, deny=["cost"])
    got = (await client.get(f"/api/v1/datasets/{ds.id}/decision-problems", headers=headers)).json()
    # With "cost" hidden one amount is left: no choice to set up is offered.
    assert got["problems"] == []
    r = await client.post(f"/api/v1/datasets/{ds.id}/decision-problems/specification", json=SAID, headers=headers)
    assert r.status_code == 403
    other = await client.get(f"/api/v1/datasets/{ds.id}/decision-problems", headers=auth_headers["b"])
    assert other.status_code in (403, 404)


# ── The third shape: levels to set, under the what-if's model ────────────────

def history(n=72, seed=3, curve=False):
    """One row per month: the outcome follows spend in a straight line (or with
    a bend), staff moves nothing."""
    rng = np.random.default_rng(seed)
    days = pd.date_range("2019-01-01", periods=n, freq="MS")
    spend = np.linspace(10.0, 60.0, n) + rng.normal(0, 1.0, n)
    staff = rng.normal(20.0, 3.0, n)
    outcome = 50 + 3.0 * spend + (0.2 * (spend - 10) ** 2 if curve else 0) + rng.normal(0, 6.0, n)
    return pd.DataFrame({"day": days, "spend": spend, "staff": staff, "outcome": outcome})


def test_a_dated_table_with_numbers_that_move_together_is_offered_levels_to_set():
    got = found(history(), {"day": "datetime", "spend": "numeric", "staff": "numeric", "outcome": "numeric"})
    assert [g["problem"] for g in got] == ["response"]
    assert got[0]["date"] == "day" and "outcome" in got[0]["measures"] and len(got[0]["factors"]) >= 2
    # Too few rows, or only one number: nothing.
    few = history(n=30)
    assert found(few, {"day": "datetime", "spend": "numeric", "staff": "numeric", "outcome": "numeric"}) == []


def test_the_model_its_ranges_and_its_doubts_are_written_down_and_nothing_is_solved():
    spec = decision.specify(history(), "response", date_col="day", objective="outcome", direction="largest",
                            factors=["spend", "staff"])
    assert spec["schema"] == decision.SCHEMA and spec["solved"] is False
    assert spec["objective"] == {"direction": "maximize", "column": "outcome", "aggregate": "total_over_horizon",
                                 "horizon": spec["objective"]["horizon"], "per": "month"}
    model = spec["model"]
    assert model["form"] == "linear" and set(model["coefficients"]) == {"spend", "staff"}
    assert 2.0 < model["coefficients"]["spend"] / 1.0 and model["r2"] > 0.8
    by = {d["name"]: d for d in spec["decisions"]}
    assert by["spend"]["lower"] == by["spend"]["observed"][0] and by["spend"]["upper"] == by["spend"]["observed"][1]
    codes = [c["code"] for c in spec["checks"]]
    # A factor that moves nothing is said to be unclear; a straight line's best is always at an end.
    assert {"code": "effect_unclear", "column": "staff", "p": next(c["p"] for c in spec["checks"] if c["code"] == "effect_unclear")} in spec["checks"]
    assert "linear_optimum_at_bounds" in codes and "association_not_intervention" in codes
    assert "bends" not in codes


def test_a_range_beyond_anything_seen_and_a_bend_are_said():
    spec = decision.specify(history(curve=True), "response", date_col="day", objective="outcome",
                            direction="largest", factors=["spend"], ranges={"spend": [0, 100000]})
    codes = [c["code"] for c in spec["checks"]]
    assert "beyond_observed" in codes and "bends" in codes
    assert spec["constraints"] == [{"kind": "range", "column": "spend", "lower": 0.0, "upper": 100000.0}]


def test_what_cannot_be_such_a_decision_is_refused_in_plain_words():
    df = history()
    for kw, said in [
        (dict(date_col="day", objective="outcome", direction="largest", factors=[]), "at least one factor"),
        (dict(date_col="day", objective="outcome", direction="largest", factors=["outcome"]), "cannot also be a factor"),
        (dict(date_col="nope", objective="outcome", direction="largest", factors=["spend"]), "date column"),
        (dict(date_col="day", objective="outcome", direction="sideways", factors=["spend"]), "large or as small"),
        (dict(date_col="day", objective="outcome", direction="largest", factors=["spend"], ranges={"spend": [5, 5]}),
         "highest level above"),
    ]:
        with pytest.raises(decision.DecisionProblemError, match=said):
            decision.specify(df, "response", **kw)


def test_a_factor_that_only_rises_with_how_busy_a_period_was_is_said():
    # Each row's units and amount are unrelated; some months simply hold more rows,
    # so the monthly totals of both rise and fall together.
    rng = np.random.default_rng(5)
    parts = []
    for m, day in enumerate(pd.date_range("2022-01-01", periods=30, freq="MS")):
        k = int(rng.integers(40, 400))
        parts.append(pd.DataFrame({"day": day + pd.to_timedelta(rng.integers(0, 27, k), unit="D"),
                                   "units": rng.uniform(1, 9, k), "amount": rng.uniform(10, 90, k)}))
    busy = pd.concat(parts, ignore_index=True)
    spec = decision.specify(busy, "response", date_col="day", objective="amount", direction="largest",
                            factors=["units"])
    assert spec["model"]["r2"] > 0.8                                   # it LOOKS like a strong model
    assert {"code": "only_volume", "column": "units"} in spec["checks"]
    # A factor that does move the number row by row is not doubted this way.
    codes = [c["code"] for c in decision.specify(history(), "response", date_col="day", objective="outcome",
                                                 direction="largest", factors=["spend"])["checks"]]
    assert "only_volume" not in codes
