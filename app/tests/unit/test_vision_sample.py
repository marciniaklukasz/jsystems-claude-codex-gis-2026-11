"""ADR-002 §4.7, D-204; PRD AC-19a, AC-19c (próbka par, podział po sequence, manifest przed żądaniem)."""

from __future__ import annotations

import hashlib

import pandas as pd

from map_qa import config, vision

TH = config.load_thresholds()


def labels(rows):
    return pd.DataFrame(rows, columns=["photo_id", "question_id", "label", "status", "sequence"])


def test_split_by_sequence_hash():
    seq = "abc"
    first = hashlib.sha256(seq.encode()).digest()[0]
    assert vision.split_of(seq) == ("validation" if first % 2 == 0 else "test")


def test_select_pairs_certain_only_balanced_and_ordered():
    rows = []
    for i in range(20):
        rows.append((f"s{i}", "speed_limit_value", "50", "certain", f"q{i % 3}"))
        rows.append((f"r{i}", "surface", "paved", "certain" if i % 4 else "uncertain", f"q{i % 5}"))
    m = vision.select_pairs(labels(rows), ["speed_limit_value", "surface"], 25)
    assert len(m) == 25
    assert (m["question_id"] == "speed_limit_value").sum() == 13 and (m["question_id"] == "surface").sum() == 12
    assert list(m["order"]) == list(range(25))
    # tylko certain
    unc = {f"r{i}" for i in range(20) if i % 4 == 0}
    assert not set(m["photo_id"]) & unc
    # cała sekwencja w jednym podziale
    assert m.groupby("sequence")["split"].nunique().max() == 1
    # kolejność w obrębie pytania po sha256(photo_id + question_id)
    sp = m[m["question_id"] == "surface"]["photo_id"].tolist()
    assert sp == sorted(sp, key=lambda p: hashlib.sha256((p + "surface").encode()).hexdigest())


def test_select_pairs_alternates_questions():
    rows = [(f"a{i}", "speed_limit_value", "50", "certain", "x") for i in range(3)] + [(f"b{i}", "surface", "paved", "certain", "y") for i in range(3)]
    m = vision.select_pairs(labels(rows), ["speed_limit_value", "surface"], 4)
    assert list(m["question_id"]) == ["speed_limit_value", "surface", "speed_limit_value", "surface"]


def test_select_pairs_fills_from_other_question_when_one_runs_out():
    rows = [("a0", "speed_limit_value", "50", "certain", "x")] + [(f"b{i}", "surface", "paved", "certain", "y") for i in range(5)]
    m = vision.select_pairs(labels(rows), ["speed_limit_value", "surface"], 4)
    assert len(m) == 4 and (m["question_id"] == "surface").sum() == 3


def test_build_sample_real_data_stage1_and_manifest_written(tmp_path, data_dir):  # AC-19c
    from map_qa import evaluation

    lab = evaluation.load_labels(data_dir)
    sample = vision.build_sample(1, 25, TH, data_dir, lab)
    m = sample.manifest
    assert len(m) == 25
    assert (m["question_id"] == "speed_limit_value").sum() == 13
    assert m["image_sha256"].str.len().eq(64).all()
    assert set(m.columns) >= {"photo_id", "question_id", "split", "sequence", "image_sha256", "order"}
    path = vision.write_manifest(m, tmp_path)
    assert path.name == "sample_manifest.csv"
    back = pd.read_csv(path, dtype=str)
    assert list(back["photo_id"]) == list(m["photo_id"])
    assert set(sample.images) == set(m["image_sha256"])


def test_build_sample_stage2_includes_stage2_questions(data_dir):  # T7.3, ADR-002 §4.1, §4.7
    from map_qa import evaluation

    sample = vision.build_sample(2, 25, TH, data_dir, evaluation.load_labels(data_dir))
    qs = sample.manifest["question_id"].value_counts().to_dict()
    assert set(qs) == {"speed_limit_value", "surface", "street_lighting_visible", "junction_visible"}
    assert len(sample.manifest) == 25 and max(qs.values()) - min(qs.values()) <= 1


def test_build_sample_rejects_photo_with_wrong_source_hash(tmp_path):  # R-F (Codex P2), ADR-002 §4.6
    import hashlib as h

    from vision_support import jpeg_bytes

    good, bad = tmp_path / "good.jpg", tmp_path / "bad.jpg"
    good.write_bytes(jpeg_bytes(400, 300))
    bad.write_bytes(jpeg_bytes(400, 301))
    lab = pd.DataFrame([
        {"photo_id": "g", "question_id": "surface", "label": "paved", "status": "certain", "sequence": "s1", "image_path": str(good),
         "expected_sha256": h.sha256(good.read_bytes()).hexdigest(), "author": "a", "license": "l", "source_url": "u"},
        {"photo_id": "b", "question_id": "surface", "label": "paved", "status": "certain", "sequence": "s2", "image_path": str(bad),
         "expected_sha256": "0" * 64, "author": "a", "license": "l", "source_url": "u"},
    ])
    s = vision.build_sample(1, 5, TH, tmp_path, lab)
    assert list(s.manifest["photo_id"]) == ["g"]
    assert s.excluded == {"niezgodny hash zdjęcia": 1}


def test_labels_carry_expected_hash(data_dir):
    from map_qa import evaluation

    lab = evaluation.load_labels(data_dir)
    assert lab["expected_sha256"].str.len().eq(64).all()
