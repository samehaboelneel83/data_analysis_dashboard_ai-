"""Persona benchmark scoring and release gate (Phase 4.1-4.2), on synthetic text."""
from app.services.persona_benchmark import check_holds, figures, gate, score_question, score_scenario


def test_figures_read_every_common_way_of_writing_a_number():
    got = figures("Total 1,175,943 refugees; 1.18M; up 79.9%; ٤٥٠ units; 45T traded")
    assert (1175943.0, False) in got and (1180000.0, False) in got and (79.9, True) in got
    assert (450.0, False) in got and (45e12, False) in got


def test_number_checks_use_a_tolerance_and_respect_percent():
    assert check_holds({"type": "number", "value": 1175943, "rel_tol": 0.02}, "now 1.18M people")
    assert not check_holds({"type": "number", "value": 1175943, "rel_tol": 0.001}, "now 1.18M people")
    assert check_holds({"type": "number", "value": 79.9, "rel_tol": 0.02, "percent": True}, "rose 80%")
    assert not check_holds({"type": "number", "value": 79.9, "rel_tol": 0.02, "percent": True}, "rose 80 points")


def test_names_directions_and_known_wrong_answers():
    assert check_holds({"type": "name", "any_of": ["North", "الشمال"]}, "Best region: الشمال (n=40)")
    text = "Members rose from 410 to 1,175 since last year. Costs fell slightly."
    assert check_holds({"type": "direction", "value": "up"}, text)
    assert check_holds({"type": "direction", "value": "down"}, text)
    assert not check_holds({"type": "direction", "value": "down"}, "Members rose.")
    assert not check_holds({"type": "none_of", "values": [243580]}, "fell to 243,580")


def test_a_question_scores_one_half_or_nothing():
    q = {"checks": [{"type": "name", "any_of": ["October"]}, {"type": "number", "value": 964178, "rel_tol": 0.02}]}
    assert score_question(q, "Best month: October, 964,178") == 1.0
    assert score_question(q, "Best month: October") == 0.5
    assert score_question(q, "Best month: March") == 0.0
    wrong = {"checks": [{"type": "name", "any_of": ["October"]}, {"type": "none_of", "values": ["first month"]}]}
    assert score_question(wrong, "The first month led with 12 orders. October came second.") == 0.5
    assert score_question(wrong, "The first month led with 12 orders.") == 0.0


def test_the_gate_refuses_a_lower_score_and_names_the_weakest():
    sc = {"id": "A", "questions": [{"id": "A.1", "checks": [{"type": "name", "any_of": ["alpha"]}]},
                                   {"id": "A.2", "checks": [{"type": "name", "any_of": ["beta"]}]}]}
    a = score_scenario(sc, "alpha only")
    b = {"id": "B", "connection": None, "score": 3.0, "out_of": 3.0, "questions": {}}
    assert a["score"] == 1.0 and a["out_of"] == 2.0
    passed = gate({"A": a, "B": b}, {"A": {"score": 1.0}, "B": {"score": 3.0}})
    assert passed["ok"] and passed["lowest"] == "A" and (passed["total"], passed["out_of"]) == (4.0, 5.0)
    failed = gate({"A": a, "B": b}, {"A": {"score": 1.5}})
    assert not failed["ok"] and failed["lowered"] == ["A"]


def test_several_runs_are_averaged_and_the_gate_allows_the_swing():
    from app.services.persona_benchmark import GATE_MARGIN, average
    run = lambda a, b: {"A": {"id": "A", "connection": None, "score": a + b, "out_of": 2.0,
                              "questions": {"A.1": a, "A.2": b}}}
    mean = average([run(1.0, 0.0), run(0.0, 0.0), run(1.0, 1.0)])["A"]
    assert mean["runs"] == 3 and mean["spread"] == 2.0
    assert abs(mean["score"] - 1.0) < 1e-9 and abs(mean["questions"]["A.1"] - 2 / 3) < 1e-9
    assert gate({"A": mean}, {"A": {"score": 1.4}}, GATE_MARGIN)["ok"]
    assert not gate({"A": mean}, {"A": {"score": 1.6}}, GATE_MARGIN)["ok"]


def test_a_wrong_name_counts_only_when_stated_with_a_figure():
    check = {"type": "none_of", "values": ["Index 30"]}
    assert not check_holds(check, "Index 30 led the ranking with 1,044,687.")
    assert check_holds(check, "Left out: “Index 30” in “ticker” — unlike the rest of that column.")
    assert check_holds(check, "Showing only 2023 — 51,100 rows. Left out: “Index 30”.")


def test_a_wrong_figure_written_as_text_counts_anywhere():
    assert not check_holds({"type": "none_of", "values": ["+83%"]}, "November grew +83% on the year.")


def test_other_quoted_names_are_not_figures():
    check = {"type": "none_of", "values": ["Index 30"]}
    assert check_holds(check, "Left out: “Index 100”, “Index 30”, “Index 70” in “ticker”.")


def test_a_wrong_name_beside_the_right_one_is_a_listing():
    q = {"checks": [{"type": "name", "any_of": ["Harbour"]}, {"type": "none_of", "values": ["Airfield"]}]}
    assert score_question(q, "Harbour has the most records with 180, Airfield with 4.") == 1.0
    assert score_question(q, "Harbour 3.5. Airfield leads with 4.50.") == 0.5          # contradicted: half
    assert score_question(q, "Airfield leads with 4.50.") == 0.0


def test_the_right_answer_beside_a_wrong_name_elsewhere_is_half():
    q = {"checks": [{"type": "name", "any_of": ["Asyut"]}, {"type": "none_of", "values": ["Siwa"]}]}
    assert score_question(q, "Highest return share: Asyut 12%. Fewest late: Siwa, 2.") == 0.5
    assert score_question(q, "Highest return share: Siwa 50%.") == 0.0
