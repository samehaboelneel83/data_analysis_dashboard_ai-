"""Unit tests for evals/run_gate.py's PURE parts -- golden loading, the
results->report plumbing, and the exit-code decision. The ask-loop itself
(live HTTP against a running agent + a real DB) needs the live stack and is
explicitly out of scope here (see run_eval_gate.ps1 / README.md for the live
smoke test) -- everything exercised below is mocked at the HTTP/executor
seam.
"""
from __future__ import annotations

import json

import pytest

from evals.run_gate import (GateInputError, annotate_strict_correct,
                            build_hand_verification_note,
                            build_operational_report, load_golden, main,
                            operational_summary, score)


# ---------------------------------------------------------------------------
# load_golden
# ---------------------------------------------------------------------------

class TestLoadGolden:
    def test_loads_valid_jsonl(self, tmp_path):
        p = tmp_path / "golden.jsonl"
        p.write_text(
            '{"question": "q1", "sql": "SELECT 1", "intent": "lookup"}\n'
            '{"question": "q2", "sql": "SELECT 2", "intent": "trend"}\n')
        rows = load_golden(str(p))
        assert len(rows) == 2
        assert rows[0] == {"question": "q1", "sql": "SELECT 1", "intent": "lookup"}

    def test_skips_blank_lines(self, tmp_path):
        p = tmp_path / "golden.jsonl"
        p.write_text('{"question": "q1", "sql": "SELECT 1", "intent": "lookup"}\n\n\n')
        assert len(load_golden(str(p))) == 1

    def test_missing_intent_defaults_to_unknown(self, tmp_path):
        p = tmp_path / "golden.jsonl"
        p.write_text('{"question": "q1", "sql": "SELECT 1"}\n')
        assert load_golden(str(p))[0]["intent"] == "unknown"

    def test_missing_file_raises_gate_input_error(self, tmp_path):
        with pytest.raises(GateInputError):
            load_golden(str(tmp_path / "nope.jsonl"))

    def test_malformed_json_raises_gate_input_error(self, tmp_path):
        p = tmp_path / "golden.jsonl"
        p.write_text("{not valid json\n")
        with pytest.raises(GateInputError):
            load_golden(str(p))

    def test_row_missing_question_raises(self, tmp_path):
        p = tmp_path / "golden.jsonl"
        p.write_text('{"sql": "SELECT 1", "intent": "lookup"}\n')
        with pytest.raises(GateInputError):
            load_golden(str(p))

    def test_row_missing_sql_raises(self, tmp_path):
        p = tmp_path / "golden.jsonl"
        p.write_text('{"question": "q1", "intent": "lookup"}\n')
        with pytest.raises(GateInputError):
            load_golden(str(p))

    def test_empty_file_raises(self, tmp_path):
        p = tmp_path / "golden.jsonl"
        p.write_text("")
        with pytest.raises(GateInputError):
            load_golden(str(p))


# ---------------------------------------------------------------------------
# score() / operational_summary() -- the results -> report plumbing
# ---------------------------------------------------------------------------

def _fake_execute(sql):
    table = {"SELECT 1": [{"n": 1}], "SELECT 2": [{"n": 2}], "": None}
    if sql == "":
        raise RuntimeError("no SQL generated")
    return table[sql]


class TestScore:
    def test_correct_and_wrong_pairs(self):
        ask_results = [
            {"golden_sql": "SELECT 1", "generated_sql": "SELECT 1", "intent": "lookup"},
            {"golden_sql": "SELECT 1", "generated_sql": "SELECT 2", "intent": "trend"},
        ]
        result = score(ask_results, _fake_execute)
        assert result["accuracy"] == 0.5
        assert result["by_intent"]["lookup"]["correct"] == 1
        assert result["by_intent"]["trend"]["correct"] == 0

    def test_missing_generated_sql_counts_wrong_not_crash(self):
        ask_results = [
            {"golden_sql": "SELECT 1", "generated_sql": None, "intent": "lookup"},
        ]
        result = score(ask_results, _fake_execute)
        assert result["correct"] == 0
        assert result["total"] == 1


class TestOperationalSummary:
    def test_counts_by_status(self):
        ask_results = [
            {"status": "ok", "latency_ms": 100},
            {"status": "ok", "latency_ms": 200},
            {"status": "needs_clarification", "latency_ms": 50},
            {"status": "failed", "latency_ms": 300},
            {"status": "error", "latency_ms": 400},
        ]
        op = operational_summary(ask_results)
        assert op["completed"] == 2
        assert op["clarification"] == 1
        assert op["failed"] == 2  # "failed" and "error" both count as not-completed
        assert op["median_latency_ms"] == 200

    def test_empty_results_no_crash(self):
        op = operational_summary([])
        assert op["completed"] == 0
        assert op["median_latency_ms"] == 0

    def test_report_line_mentions_all_four_metrics(self):
        op = {"completed": 4, "clarification": 1, "failed": 0, "median_latency_ms": 123}
        line = build_operational_report(op, 5)
        assert "4/5" in line
        assert "123" in line


class TestAnnotateStrictCorrect:
    def test_marks_only_wrong_ones_incorrect(self):
        ask_results = [
            {"golden_sql": "SELECT 1", "generated_sql": "SELECT 1",
             "intent": "lookup", "question": "q1", "status": "ok", "repair_attempts": 0},
            {"golden_sql": "SELECT 1", "generated_sql": "SELECT 2",
             "intent": "trend", "question": "q2", "status": "ok", "repair_attempts": 1},
            {"golden_sql": "SELECT 1", "generated_sql": None,
             "intent": "compare", "question": "q3", "status": "needs_clarification",
             "repair_attempts": 0},
        ]
        annotated = annotate_strict_correct(ask_results, _fake_execute)
        by_q = {r["question"]: r["strict_correct"] for r in annotated}
        assert by_q == {"q1": True, "q2": False, "q3": False}

    def test_note_lists_sql_for_wrong_questions(self):
        ask_results = [
            {"golden_sql": "SELECT 1", "generated_sql": "SELECT 2",
             "intent": "trend", "question": "q2", "status": "ok", "repair_attempts": 1},
        ]
        annotated = annotate_strict_correct(ask_results, _fake_execute)
        note = build_hand_verification_note(annotated)
        assert "q2" in note
        assert "SELECT 1" in note
        assert "SELECT 2" in note

    def test_note_says_none_when_all_correct(self):
        ask_results = [
            {"golden_sql": "SELECT 1", "generated_sql": "SELECT 1",
             "intent": "lookup", "question": "q1", "status": "ok", "repair_attempts": 0},
        ]
        annotated = annotate_strict_correct(ask_results, _fake_execute)
        note = build_hand_verification_note(annotated)
        assert "none" in note.lower()


# ---------------------------------------------------------------------------
# main() -- the exit-code decision, with the ask-loop/DB/executor seams mocked
# ---------------------------------------------------------------------------

class TestMainExitCodes:
    def _golden_file(self, tmp_path):
        p = tmp_path / "golden.jsonl"
        p.write_text('{"question": "q1", "sql": "SELECT 1", "intent": "lookup"}\n')
        return str(p)

    def _patch_stack(self, monkeypatch, *, accuracy_ok: bool):
        import evals.run_gate as gate

        async def fake_ask_loop(golden, source_id):
            gen = "SELECT 1" if accuracy_ok else "SELECT 2"
            return [{**golden[0], "golden_sql": golden[0]["sql"], "status": "ok",
                     "generated_sql": gen, "repair_attempts": 0, "latency_ms": 10,
                     "error": None}]

        async def fake_source_cfg(source_id):
            return {"type": "sqlite"}

        def fake_make_executor(cfg):
            return _fake_execute

        monkeypatch.setattr(gate, "run_ask_loop", fake_ask_loop)
        monkeypatch.setattr(gate, "_source_cfg", fake_source_cfg)
        monkeypatch.setattr(gate, "make_executor", fake_make_executor)

    def test_exit_0_when_accuracy_at_or_above_threshold(self, tmp_path, monkeypatch, capsys):
        self._patch_stack(monkeypatch, accuracy_ok=True)
        golden = self._golden_file(tmp_path)
        out = tmp_path / "results.json"
        rc = main(["--source-id", "2", "--golden", golden,
                  "--min-accuracy", "1.0", "--out", str(out)])
        assert rc == 0
        payload = json.loads(out.read_text())
        assert payload["summary"]["accuracy"] == 1.0
        assert "OVERALL" in capsys.readouterr().out

    def test_exit_1_when_accuracy_below_threshold(self, tmp_path, monkeypatch):
        self._patch_stack(monkeypatch, accuracy_ok=False)
        golden = self._golden_file(tmp_path)
        out = tmp_path / "results.json"
        rc = main(["--source-id", "2", "--golden", golden,
                  "--min-accuracy", "1.0", "--out", str(out)])
        assert rc == 1

    def test_exit_2_on_missing_golden_file(self, tmp_path, capsys):
        rc = main(["--source-id", "2", "--golden", str(tmp_path / "nope.jsonl")])
        assert rc == 2
        assert "error" in capsys.readouterr().err.lower()

    def test_exit_2_on_bad_source_id(self, tmp_path):
        golden = self._golden_file(tmp_path)
        rc = main(["--source-id", "0", "--golden", golden])
        assert rc == 2

    def test_value_verified_flag_prints_hand_verification_section(
            self, tmp_path, monkeypatch, capsys):
        self._patch_stack(monkeypatch, accuracy_ok=False)
        golden = self._golden_file(tmp_path)
        out = tmp_path / "results.json"
        main(["--source-id", "2", "--golden", golden, "--min-accuracy", "0.0",
             "--out", str(out), "--value-verified"])
        assert "Hand-verification candidates" in capsys.readouterr().out

    def test_writes_raw_per_question_results(self, tmp_path, monkeypatch):
        self._patch_stack(monkeypatch, accuracy_ok=True)
        golden = self._golden_file(tmp_path)
        out = tmp_path / "results.json"
        main(["--source-id", "2", "--golden", golden, "--min-accuracy", "0.0",
             "--out", str(out)])
        payload = json.loads(out.read_text())
        assert payload["questions"][0]["question"] == "q1"
        assert payload["operational"]["completed"] == 1

    def test_out_json_annotates_strict_correct_per_question(self, tmp_path, monkeypatch):
        self._patch_stack(monkeypatch, accuracy_ok=False)
        golden = self._golden_file(tmp_path)
        out = tmp_path / "results.json"
        main(["--source-id", "2", "--golden", golden, "--min-accuracy", "0.0",
             "--out", str(out)])
        payload = json.loads(out.read_text())
        # accuracy_ok=False means the fake ask-loop generated "SELECT 2" against
        # golden "SELECT 1" -- strict_correct must reflect that per-row, not
        # just be present.
        assert payload["questions"][0]["strict_correct"] is False
