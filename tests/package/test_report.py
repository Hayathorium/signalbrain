import json
from pathlib import Path
from signalbrain.report import run_report

def test_report_generation_and_honesty_metrics(tmp_path: Path):
    # 1. Arrange: Create a mock ledger with mixed data
    ledger_file = tmp_path / "mock_ledger.jsonl"
    mock_rows = [
        {"receipt_id": "rcpt-1", "confidence": 0.82, "held": True, "claim_kind": "standard", "scored_by": "measured"},
        {"receipt_id": "rcpt-2", "confidence": 0.92, "held": False, "claim_kind": "standard", "scored_by": "measured"},
        {"receipt_id": "rcpt-3", "confidence": 0.97, "held": True, "claim_kind": "standard", "scored_by": "measured"},
        {"receipt_id": "pin-1", "confidence": 1.0, "held": True, "claim_kind": "invariant_pin"},
        {"receipt_id": "unmeasured-1", "confidence": 0.5, "held": False, "measured": False}
    ]
    
    with open(ledger_file, "w", encoding="utf-8") as f:
        for row in mock_rows:
            f.write(json.dumps(row) + "\n")

    # 2. Arrange: Create a dummy receipts directory
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir()
    
    # Create a simple mock markdown receipt for rcpt-1 containing one command block
    rcpt_1_file = receipts_dir / "rcpt-1.md"
    rcpt_1_file.write_text("```bash\npytest\n```")

    # Destination directory for the final outputs
    out_dir = tmp_path / "output_report"

    # 3. Act: Execute the target core reporting pipeline
    run_report(ledger_path=ledger_file, receipts_dir=receipts_dir, out_dir=out_dir)

    # 4. Assert: Verify the core deliverables are present
    assert (out_dir / "bins.json").is_file()
    assert (out_dir / "report.md").is_file()

    # 5. Assert: Verify the "Honesty Rules" accurately parsed the metrics
    with open(out_dir / "bins.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert data["total_measured_rows"] == 3
    assert data["exclusions"]["invariant_pin"] == 1
    assert data["exclusions"]["unmeasured"] == 1