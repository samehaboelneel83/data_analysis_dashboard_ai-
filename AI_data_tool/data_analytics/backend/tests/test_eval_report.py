"""T9: evals/report.py turns evaluate()'s results dict into a table and a pass/fail
gate — the missing piece that made evals/run_eval.py "a library, not a gate."
"""
import json

import pytest

from evals.report import build_report, main


def _results(accuracy=0.75):
    return {
        "total": 4, "correct": 3, "accuracy": accuracy,
        "by_intent": {
            "lookup": {"total": 2, "correct": 2},
            "trend": {"total": 2, "correct": 1},
        },
    }


class TestBuildReport:
    def test_table_has_a_row_per_intent(self):
        table = build_report(_results())
        assert "lookup" in table
        assert "trend" in table

    def test_table_has_an_overall_row(self):
        table = build_report(_results())
        assert "OVERALL" in table

    def test_per_intent_counts_are_correct(self):
        table = build_report(_results())
        lookup_line = next(l for l in table.splitlines() if l.strip().startswith("lookup"))
        assert "2" in lookup_line  # correct
        trend_line = next(l for l in table.splitlines() if l.strip().startswith("trend"))
        assert "1" in trend_line

    def test_handles_empty_by_intent(self):
        table = build_report({"total": 0, "correct": 0, "accuracy": 0.0, "by_intent": {}})
        assert "OVERALL" in table


class TestMainGate:
    def test_exit_1_below_threshold(self, tmp_path):
        p = tmp_path / "results.json"
        p.write_text(json.dumps(_results(accuracy=0.4)))
        assert main([str(p), "--min-accuracy", "0.5"]) == 1

    def test_exit_0_at_threshold(self, tmp_path):
        p = tmp_path / "results.json"
        p.write_text(json.dumps(_results(accuracy=0.5)))
        assert main([str(p), "--min-accuracy", "0.5"]) == 0

    def test_exit_0_above_threshold(self, tmp_path):
        p = tmp_path / "results.json"
        p.write_text(json.dumps(_results(accuracy=0.9)))
        assert main([str(p), "--min-accuracy", "0.5"]) == 0

    def test_default_threshold_is_permissive(self, tmp_path):
        p = tmp_path / "results.json"
        p.write_text(json.dumps(_results(accuracy=0.0)))
        assert main([str(p)]) == 0

    def test_malformed_json_exits_2(self, tmp_path, capsys):
        p = tmp_path / "results.json"
        p.write_text("{not valid json")
        assert main([str(p)]) == 2
        assert "error" in capsys.readouterr().err.lower()

    def test_missing_accuracy_key_exits_2(self, tmp_path, capsys):
        p = tmp_path / "results.json"
        p.write_text(json.dumps({"total": 1, "correct": 1}))
        assert main([str(p)]) == 2
        assert "error" in capsys.readouterr().err.lower()

    def test_missing_file_exits_2(self, tmp_path, capsys):
        assert main([str(tmp_path / "nope.json")]) == 2
        assert "error" in capsys.readouterr().err.lower()
