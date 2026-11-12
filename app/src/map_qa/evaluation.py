"""Label loading and read quality metrics."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


LABEL_COLUMNS = ["photo_id", "question_id", "label", "status", "sequence", "image_path", "author", "license", "source_url"]


def _csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8", keep_default_na=False)


def _image_path(data_dir: Path, *candidates: Path) -> str | None:
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def load_labels(data_dir: str | Path) -> pd.DataFrame:
    root = Path(data_dir)
    signs = _csv(root / "signs" / "signs.csv").set_index("photo_id", drop=False)
    speed_rows = []
    for row in _csv(root / "signs" / "labels.csv").to_dict("records"):
        photo_id = row["photo_id"]
        sign = signs.loc[photo_id] if photo_id in signs.index else {}
        if isinstance(sign, pd.DataFrame):
            sign = sign.iloc[0]
        speed_rows.append({
            "photo_id": photo_id, "question_id": "speed_limit_value", "label": row["sign_value"], "status": row["status"],
            "sequence": sign.get("sequence", ""), "image_path": _image_path(root, root / "signs" / "photos" / f"{photo_id}.jpg"),
            "author": sign.get("creator", ""), "license": sign.get("license", ""), "source_url": sign.get("source_url", ""),
        })

    photos = _csv(root / "photos.csv").set_index("photo_id", drop=False)
    rows = list(speed_rows)
    for row in _csv(root / "reference_labels.csv").to_dict("records"):
        if row["question"] == "speed_limit_value":
            continue
        photo_id = row["photo_id"]
        photo = photos.loc[photo_id] if photo_id in photos.index else {}
        if isinstance(photo, pd.DataFrame):
            photo = photo.iloc[0]
        filename = photo.get("filename", "")
        rows.append({
            "photo_id": photo_id, "question_id": row["question"], "label": row["label"], "status": row["status"],
            "sequence": photo.get("sequence", ""),
            "image_path": _image_path(root, root / "offline" / filename, root / "data" / "photos" / filename) if filename else None,
            "author": photo.get("author", ""), "license": photo.get("license", ""), "source_url": photo.get("source_url", ""),
        })
    return pd.DataFrame(rows, columns=LABEL_COLUMNS)


def _truth(value) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _clean(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def evaluate(readings: pd.DataFrame, labels: pd.DataFrame, comparison: pd.DataFrame | None = None) -> dict:
    certain_labels = labels[labels["status"].astype(str).str.strip().eq("certain")]
    result = {}
    read_qids = readings["question_id"].drop_duplicates().tolist() if len(readings) else []
    for qid in read_qids:
        all_q_labels = labels[labels.question_id == qid]
        pairs = certain_labels[certain_labels.question_id == qid]
        merged = pairs.merge(readings[readings.question_id == qid], on=["photo_id", "question_id"], how="inner", suffixes=("_label", "_reading"))
        splits = list(dict.fromkeys(merged["split"].tolist()))
        split_values = [*splits, "all"]
        rows = []
        sources = [("decision", "decision_answer", lambda r: _truth(r["decision_confident"])),
                   ("after_escalation", "answer", lambda r: str(r["status_reading"]).strip() == "certain")]
        if comparison is not None and not comparison.empty:
            sources.append(("comparison", "answer_cmp", lambda r: _truth(r["confident"])))
            cmp = comparison[comparison.question_id == qid].rename(columns={"answer": "answer_cmp"})
            merged = merged.merge(cmp[["photo_id", "question_id", "split", "answer_cmp", "confident"]], on=["photo_id", "question_id", "split"], how="left")
        if "status_reading" not in merged.columns:
            merged["status_reading"] = merged["status"]
        for split in split_values:
            subset = merged if split == "all" else merged[merged.split == split]
            pair_count = len(subset)
            for who, answer_col, confident in sources:
                certain = correct = 0
                for record in subset.to_dict("records"):
                    if confident(record):
                        certain += 1
                        answer = record.get(answer_col, "")
                        correct += _clean(answer) == _clean(record["label"])
                rows.append({"split": split, "who": who, "pairs": pair_count, "certain": certain, "correct": correct,
                             "coverage": round(certain / pair_count, 3) if pair_count else None,
                             "accuracy": round(correct / certain, 3) if certain else None})
        result[qid] = {"pairs": len(merged), "uncertain_labels_excluded": int((all_q_labels.status == "uncertain").sum()), "rows": rows}
    return result


def thresholds_met(result: dict, th: dict) -> dict:
    evaluation_thresholds = th["evaluation"]
    out = {}
    for qid, data in result.items():
        row = next((r for r in data["rows"] if r["who"] == "after_escalation" and r["split"] == "all"), None)
        if row is None or row["coverage"] is None or row["accuracy"] is None:
            out[qid] = None
        else:
            out[qid] = row["coverage"] >= evaluation_thresholds["min_coverage"] and row["accuracy"] >= evaluation_thresholds["min_accuracy"]
    return out
