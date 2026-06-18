#!/usr/bin/env python3
"""评估对比：把两个预测文件和样本真值对齐，输出准确率对比。

用法：
    python src/evaluate.py \\
        --before results/predictions_v1.json.json \\
        --after  results/predictions_v2.json.json \\
        --output results/eval_compare.json
"""
import argparse
import json
from pathlib import Path


def load_json(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def accuracy(samples: list, preds: list) -> tuple[int, int]:
    """返回 (正确数, 总数)。按 id 对齐，label 取自 samples。"""
    pred_map = {p["id"]: p.get("predicted_category", "") for p in preds}
    correct = sum(1 for s in samples if pred_map.get(s["id"]) == s["label"])
    return correct, len(samples)


def main() -> None:
    p = argparse.ArgumentParser(description="v1 vs v2 准确率对比")
    p.add_argument(
        "--samples",
        default="original_files/task1_test_samples.json",
        help="样本文件（含 label 真值）",
    )
    p.add_argument("--before", required=True, help="改进前预测文件")
    p.add_argument("--after", required=True, help="改进后预测文件")
    p.add_argument("--output", help="结果写入 JSON")
    args = p.parse_args()

    samples = load_json(args.samples)
    b_correct, b_total = accuracy(samples, load_json(args.before))
    a_correct, a_total = accuracy(samples, load_json(args.after))
    b_acc = b_correct / b_total
    a_acc = a_correct / a_total

    print(f"Before (v1): {b_correct}/{b_total} = {b_acc:.3f}")
    print(f"After  (v2): {a_correct}/{a_total} = {a_acc:.3f}")
    print(f"Delta      : {a_acc - b_acc:+.3f}")

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({
                "before": {"correct": b_correct, "total": b_total, "accuracy": b_acc},
                "after": {"correct": a_correct, "total": a_total, "accuracy": a_acc},
                "delta_accuracy": a_acc - b_acc,
            }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
