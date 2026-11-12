from __future__ import annotations

import pandas as pd

from map_qa.evaluation import evaluate, load_labels, thresholds_met


def test_evaluate_pairs_coverage_accuracy_and_uncertain_exclusion():
    labels = pd.DataFrame([
        {"photo_id": str(i), "question_id": "surface", "label": str(i % 2), "status": "certain"}
        for i in range(4)
    ] + [{"photo_id": "x", "question_id": "surface", "label": "1", "status": "uncertain"}])
    readings = pd.DataFrame([
        {"photo_id": str(i), "question_id": "surface", "split": "test", "decision_answer": ("1" if i == 2 else str(i % 2)), "decision_confident": i < 3, "answer": "0" if i < 3 else "", "status": "certain" if i < 3 else "uncertain"}
        for i in range(4)
    ])
    result = evaluate(readings, labels)
    assert result["surface"]["pairs"] == 4
    assert result["surface"]["uncertain_labels_excluded"] == 1
    decision = next(r for r in result["surface"]["rows"] if r["who"] == "decision" and r["split"] == "all")
    assert (decision["pairs"], decision["certain"], decision["correct"]) == (4, 3, 2)
    assert decision["coverage"] == 0.75
    assert decision["accuracy"] == 0.667


def test_zero_certain_accuracy_is_none_and_threshold_missing_is_none():
    labels = pd.DataFrame([{"photo_id": "1", "question_id": "surface", "label": "paved", "status": "certain"}])
    readings = pd.DataFrame([{"photo_id": "1", "question_id": "surface", "split": "a", "decision_answer": "", "decision_confident": False, "answer": "", "status": "uncertain"}])
    result = evaluate(readings, labels)
    row = next(r for r in result["surface"]["rows"] if r["who"] == "after_escalation" and r["split"] == "all")
    assert row["accuracy"] is None
    assert thresholds_met(result, {"evaluation": {"min_coverage": 0.8, "min_accuracy": 0.8}})["surface"] is None


def test_comparison_and_text_stripping():
    labels = pd.DataFrame([{"photo_id": "1", "question_id": "surface", "label": " paved ", "status": "certain"}])
    readings = pd.DataFrame([{"photo_id": "1", "question_id": "surface", "split": "train", "decision_answer": "paved", "decision_confident": True, "answer": "paved", "status": "certain"}])
    comparison = pd.DataFrame([{"photo_id": "1", "question_id": "surface", "split": "train", "answer": " paved ", "confident": True}])
    result = evaluate(readings, labels, comparison)
    row = next(r for r in result["surface"]["rows"] if r["who"] == "comparison" and r["split"] == "all")
    assert row["correct"] == 1 and row["accuracy"] == 1.0


def test_load_labels_from_real_data(data_dir):
    labels = load_labels(data_dir)
    assert list(labels.columns) == ["photo_id", "question_id", "label", "status", "sequence", "image_path", "author", "license", "source_url"]
    speed = labels[labels.question_id == "speed_limit_value"]
    assert len(speed[speed.status == "certain"]) == 115
    assert speed.image_path.map(lambda p: bool(p) and __import__("pathlib").Path(p).is_file()).all()
    assert len(speed) == len(pd.read_csv(data_dir / "signs" / "labels.csv", dtype=str))
    surface = labels[(labels.question_id == "surface") & (labels.status == "certain")]
    assert len(surface) == 99


def test_pairs_count_sample_pairs_not_all_labels_and_only_read_questions():  # AC-23: liczone na parach próbki
    import pandas as pd
    from map_qa import evaluation as ev_mod

    labels = pd.DataFrame([
        {"photo_id": f"p{i}", "question_id": "surface", "label": "paved", "status": "certain"} for i in range(10)
    ] + [{"photo_id": "x", "question_id": "junction_visible", "label": "yes", "status": "certain"}])
    readings = pd.DataFrame([{"photo_id": "p0", "question_id": "surface", "split": "test", "decision_answer": "paved",
                              "decision_confident": True, "answer": "paved", "status": "certain"}])
    out = ev_mod.evaluate(readings, labels)
    assert list(out) == ["surface"]
    assert out["surface"]["pairs"] == 1
