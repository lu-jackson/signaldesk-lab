"""合成資料評估：Demo 規則分類器 vs 人工標註 fixtures（fixtures 與 runtime 規則分離，規則看不到標註）。

python -m eval.evaluate           # 印出報告
零分母時回傳 None，報告顯示 n/a，不偽裝成 0 或 1。
這是 36 筆合成句子的小型評估，不代表真實世界的準確度。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.providers.ai_demo import classify_text

FIX = Path(__file__).parent / "fixtures.json"
INTENTS = ["seeking", "advice", "promotion", "complaint", "other"]


def _ratio(n: int, d: int):
    return None if d == 0 else round(n / d, 3)


def evaluate(fixtures: list[dict] | None = None) -> dict:
    fixtures = fixtures or json.loads(FIX.read_text(encoding="utf-8"))
    pairs = [(f, classify_text(f["text"])) for f in fixtures]
    cm: dict[str, Counter] = {i: Counter() for i in INTENTS}
    for f, c in pairs:
        cm[f["intent"]][c.intent] += 1
    per_class = {}
    for i in INTENTS:
        tp = cm[i][i]
        fp = sum(cm[o][i] for o in INTENTS if o != i)
        fn = sum(v for k, v in cm[i].items() if k != i)
        per_class[i] = {"tp": tp, "fp": fp, "fn": fn, "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn), "support": tp + fn}
    rel_tp = sum(1 for f, c in pairs if f["relevant"] and c.relevant)
    rel_fp = sum(1 for f, c in pairs if not f["relevant"] and c.relevant)
    rel_fn = sum(1 for f, c in pairs if f["relevant"] and not c.relevant)
    risk_ok = sum(1 for f, c in pairs if f["risk"] == c.risk)
    misses = [{"id": f["id"], "text": f["text"], "expected": f["intent"], "got": c.intent} for f, c in pairs if f["intent"] != c.intent]
    return {
        "n": len(pairs),
        "intent_accuracy": _ratio(sum(1 for f, c in pairs if f["intent"] == c.intent), len(pairs)),
        "confusion_matrix": {"labels": INTENTS, "rows_are": "人工標註", "cols_are": "規則預測", "matrix": [[cm[r][c] for c in INTENTS] for r in INTENTS]},
        "per_class": per_class,
        "relevant": {"precision": _ratio(rel_tp, rel_tp + rel_fp), "recall": _ratio(rel_tp, rel_tp + rel_fn), "tp": rel_tp, "fp": rel_fp, "fn": rel_fn},
        "risk_exact_match": {"rate": _ratio(risk_ok, len(pairs)), "matched": risk_ok, "of": len(pairs)},
        "misclassified": misses,
        "disclaimer": "36 筆合成句子；不代表真實社群資料或商業成效",
    }


def main() -> None:
    r = evaluate()
    print(f"n={r['n']}  intent accuracy={r['intent_accuracy']}")
    print("confusion (rows=人工, cols=規則):", r["confusion_matrix"]["labels"])
    for lab, row in zip(r["confusion_matrix"]["labels"], r["confusion_matrix"]["matrix"]):
        print(f"  {lab:10s}", row)
    for k, v in r["per_class"].items():
        print(f"  {k:10s} precision={v['precision']} recall={v['recall']} support={v['support']}")
    print("relevant:", r["relevant"])
    print("risk exact:", r["risk_exact_match"])
    for m in r["misclassified"]:
        print("  MISS", m)


if __name__ == "__main__":
    main()
