from __future__ import annotations

from pathlib import Path

from app.strategy.proof_of_winning_calibration import CalibrationArtifacts, load_trades_dataframe, summarize_proof_of_winning_trades


def write_calibration_report(sqlite_path: Path, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    trades = load_trades_dataframe(sqlite_path)
    artifacts = summarize_proof_of_winning_trades(trades)
    csv_path = output_dir / "proof_of_winning_calibration_by_group.csv"
    md_path = output_dir / "proof_of_winning_calibration_summary.md"
    write_group_csv(csv_path, artifacts)
    write_summary_md(md_path, artifacts)
    return csv_path, md_path


def write_group_csv(path: Path, artifacts: CalibrationArtifacts) -> None:
    import pandas as pd

    frames: list[pd.DataFrame] = []
    for label, frame in [
        ("league", artifacts.by_league),
        ("entry_bucket", artifacts.by_entry_bucket),
        ("market_type", artifacts.by_market_type),
        ("entry_reason", artifacts.by_reason),
    ]:
        if frame.empty:
            continue
        tagged = frame.copy()
        tagged.insert(0, "section", label)
        frames.append(tagged)
    if not frames:
        path.write_text("no rows\n", encoding="utf-8")
        return
    combined = pd.concat(frames, ignore_index=True)
    combined.to_csv(path, index=False)


def write_summary_md(path: Path, artifacts: CalibrationArtifacts) -> None:
    lines = [
        "# Proof Of Winning Calibration",
        "",
        f"- total: {artifacts.summary['total']}",
        f"- resolved: {artifacts.summary['resolved']}",
        f"- wins: {artifacts.summary['wins']}",
        f"- losses: {artifacts.summary['losses']}",
        f"- pnl_usd: {artifacts.summary['pnl_usd']}",
        f"- win_rate: {artifacts.summary['win_rate']}",
        "",
    ]
    for title, frame in [
        ("By League", artifacts.by_league),
        ("By Entry Bucket", artifacts.by_entry_bucket),
        ("By Market Type", artifacts.by_market_type),
        ("By Reason", artifacts.by_reason),
    ]:
        lines.append(f"## {title}")
        lines.append("")
        if frame.empty:
            lines.append("no rows")
            lines.append("")
            continue
        lines.append(frame.to_markdown(index=False))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")

