# src/signalbrain/report.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signalbrain.ledger import load_rows, filter_rows, is_goodhart_excluded_row
from signalbrain.receipt import extract_commands_with_env

BINS = [(0.80, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 1.01)]

def calculate_bins(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for lo, hi in BINS:
        sub = [r for r in rows if lo <= float(r.get("confidence", 0)) < hi]
        held = sum(1 for r in sub if r.get("held"))
        out.append({
            "bin": f"[{lo:.2f},{min(hi,1.0):.2f})",
            "mid": (lo + min(hi, 1.0)) / 2,
            "n": len(sub),
            "held": held,
            "hold_rate": round(held / len(sub), 3) if sub else None,
        })
    return out

def generate_markdown_table(result: dict[str, Any]) -> str:
    md = ["### Overall Reliability\n", "| Bin | Midpoint | n | Held | Hold-Rate |", "|---|---|---|---|---|"]
    for b in result["overall"]:
        hr = f"{b['hold_rate']:.3f}" if b['hold_rate'] is not None else "N/A"
        md.append(f"| {b['bin']} | {b['mid']:.2f} | {b['n']} | {b['held']} | {hr} |")
    
    md.append("\n### By Difficulty Stratification\n")
    md.append("| Stratum | n | Held | Hold-Rate |")
    md.append("|---|---|---|---|")
    for k, v in result["by_difficulty"].items():
        hr = f"{v['hold_rate']:.3f}" if v['hold_rate'] is not None else "N/A"
        md.append(f"| {k} | {v['n']} | {v['held']} | {hr} |")
        
    md.append(f"\n**Exclusions (Honesty Counter):**")
    md.append(f"* invariant_pin count: {result['exclusions']['invariant_pin']}")
    md.append(f"* unmeasured count: {result['exclusions']['unmeasured']}")
    return "\n".join(md)

def run_report(ledger_path: Path, receipts_dir: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    all_rows = load_rows(ledger_path)
    
    # 1. Honesty Rules: use the SAME predicate as the trust gate so the report
    #    and the gate always tell the same story (filter_rows require_measured).
    measured_rows = filter_rows(all_rows, require_measured=True)
    excluded_pins = sum(1 for r in all_rows if is_goodhart_excluded_row(r))
    excluded_unmeasured = sum(
        1 for r in all_rows
        if r.get("scored_by") != "measured" and not is_goodhart_excluded_row(r)
    )
    
    # 2. Extract Difficulty Metrics
    for r in measured_rows:
        rid = str(r.get("receipt_id") or r.get("claim") or "")
        f = receipts_dir / f"{rid}.md"
        if f.is_file():
            _, cmds = extract_commands_with_env(f.read_text(encoding="utf-8"))
            r["_n_cmds"] = len(cmds)
        else:
            r["_n_cmds"] = None

    result = {
        "total_measured_rows": len(measured_rows),
        "exclusions": {
            "invariant_pin": excluded_pins,
            "unmeasured": excluded_unmeasured
        },
        "overall": calculate_bins(measured_rows),
        "by_class": {},
        "by_difficulty": {}
    }

    # Populate change classes
    classes = sorted({str(r.get("change_class") or "unclassified") for r in measured_rows})
    for c in classes:
        crows = [r for r in measured_rows if str(r.get("change_class") or "unclassified") == c]
        result["by_class"][c] = {"n": len(crows), "bins": calculate_bins(crows)}

    # Difficulty strata
    strata = {
        "1 command": [r for r in measured_rows if r["_n_cmds"] == 1],
        "2+ commands": [r for r in measured_rows if (r["_n_cmds"] or 0) >= 2],
        "receipt missing": [r for r in measured_rows if r["_n_cmds"] is None]
    }
    for k, sub in strata.items():
        held = sum(1 for r in sub if r.get("held"))
        rate = held / len(sub) if sub else 0
        result["by_difficulty"][k] = {"n": len(sub), "held": held, "hold_rate": round(rate, 3) if sub else None}

    # Write fallback JSON and Markdown deliverables
    (out_dir / "bins.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (out_dir / "report.md").write_text(generate_markdown_table(result) + "\n", encoding="utf-8")

    # 3. Optional visual plots rendering path
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        
        # Color palette setup
        FG, BG, ACC, RED, MUT = "#eef2f7", "#0d1117", "#34d399", "#f87171", "#94a3b8"
        
        def style(ax, title):
            ax.set_facecolor(BG)
            ax.figure.set_facecolor(BG)
            for s in ax.spines.values():
                s.set_color("#2a2f3a")
            ax.tick_params(colors=MUT)
            ax.set_title(title, color=FG, fontsize=11)
            ax.xaxis.label.set_color(MUT)
            ax.yaxis.label.set_color(MUT)

        # Map internal variable context cleanly
        rows = measured_rows

        # 1. overall reliability
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        b = result["overall"]
        xs = [x["mid"] for x in b if x["n"]]
        ys = [x["hold_rate"] for x in b if x["n"]]
        ns = [x["n"] for x in b if x["n"]]
        ax.plot([0.8, 1.0], [0.8, 1.0], "--", color=MUT, lw=1, label="perfect calibration")
        ax.plot(xs, ys, "o-", color=ACC, lw=2, ms=7)
        for x, y, n in zip(xs, ys, ns):
            ax.annotate(f"n={n}", (x, y), textcoords="offset points", xytext=(6, -14), color=MUT, fontsize=8)
        ax.set_xlabel("stated confidence (bin midpoint)")
        ax.set_ylabel("observed hold-rate")
        ax.set_ylim(0, 1.05)
        style(ax, "Reliability: stated confidence vs measured hold-rate (all measured claims)")
        ax.legend(facecolor=BG, labelcolor=FG, edgecolor="#2a2f3a", fontsize=8)
        fig.tight_layout(); fig.savefig(out_dir / "reliability.png", dpi=150); plt.close(fig)

        # 2. per-class
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        ax.plot([0.8, 1.0], [0.8, 1.0], "--", color=MUT, lw=1)
        palette = [ACC, "#7cc0ff", "#f0b849", RED, "#bf5af2", MUT]
        for i, c in enumerate(classes):
            cb = result["by_class"][c]["bins"]
            xs = [x["mid"] for x in cb if x["n"]]
            ys = [x["hold_rate"] for x in cb if x["n"]]
            if xs:
                ax.plot(xs, ys, "o-", lw=1.6, ms=5, label=f"{c} (n={result['by_class'][c]['n']})", color=palette[i % len(palette)])
        ax.set_xlabel("stated confidence (bin midpoint)"); ax.set_ylabel("observed hold-rate"); ax.set_ylim(0, 1.05)
        style(ax, "Reliability by change-class")
        ax.legend(facecolor=BG, labelcolor=FG, edgecolor="#2a2f3a", fontsize=8)
        fig.tight_layout(); fig.savefig(out_dir / "by_class.png", dpi=150); plt.close(fig)

        # 3. difficulty proxy: measure-command count
        fig, ax = plt.subplots(figsize=(6.5, 4.0))
        labels, rates = [], []
        for k, sub in strata.items():
            labels.append(f"{k}\nn={len(sub)}")
            rates.append(result["by_difficulty"][k]["hold_rate"] or 0)
        bars = ax.bar(labels, rates, color=[ACC, "#7cc0ff", MUT], width=0.55)
        for bar, r in zip(bars, rates):
            ax.annotate(f"{r:.0%}", (bar.get_x() + bar.get_width() / 2, r), ha="center", va="bottom", color=FG, fontsize=10)
        ax.set_ylabel("hold-rate"); ax.set_ylim(0, 1.1)
        style(ax, "Hold-rate by difficulty proxy (measure-command count)")
        fig.tight_layout(); fig.savefig(out_dir / "by_difficulty.png", dpi=150); plt.close(fig)
        
        print(f"Generated analytics curves and JSON artifacts inside {out_dir}/")
    except ImportError:
        print(f"Generated raw text summary report and JSON data inside {out_dir}/.")
        print("Note: Install 'matplotlib' to generate visual PNG curves next time.")