"""
Generate reports from matching results.
"""

from typing import List, Dict
from pathlib import Path
import json
import logging

from matcher import MatchResult, CONFIDENCE_HIGH, CONFIDENCE_MEDIUM

log = logging.getLogger(__name__)


def format_duration(seconds: int) -> str:
    """Format seconds as human-readable duration (e.g., 42m 15s)"""
    if seconds < 0:
        return "unknown"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def generate_text_report(
    results: List[MatchResult],
    show: str,
    season: int,
    disk: int,
) -> str:
    """
    Generate a human-readable text report.

    Returns a formatted string report with:
    - All matched files with confidence levels
    - Flagged files (collisions, medium/low confidence, unmatched)
    - Summary statistics
    """

    lines = []
    lines.append("=" * 80)
    lines.append(f"DISK RIPPING REPORT: {show} S{season:02d}D{disk:02d}")
    lines.append("=" * 80)
    lines.append("")

    # Categorize results
    high_conf = [r for r in results if r.confidence == "high"]
    medium_conf = [r for r in results if r.confidence == "medium"]
    low_conf = [r for r in results if r.confidence == "low"]
    no_match = [r for r in results if r.confidence == "no_match"]

    # Detect ambiguities: collisions (multiple matches <5s delta where duration differs)
    # Only flag if the file duration is genuinely ambiguous (not just TMDb having identical runtimes)
    collisions = [
        r for r in results
        if r.confidence != "no_match" and len(r.all_candidates) > 1
        and r.all_candidates[0][1] <= 5
        and any(c[1] <= 5 for c in r.all_candidates[1:])
    ]

    # Flagged files: collisions + medium/low confidence (as list, avoiding set issues)
    flagged_files = collisions + medium_conf + low_conf

    # Matched files section
    lines.append("MATCHED FILES")
    lines.append("-" * 80)
    if not results or all(r.confidence == "no_match" for r in results):
        lines.append("  (No matches)")
    else:
        for result in results:
            if result.confidence != "no_match":
                file_dur = format_duration(result.file.duration_seconds)
                target_dur = format_duration(result.matched_episode.runtime_seconds)
                delta_str = format_duration(result.delta_seconds)

                flag = "⚠️ " if result in flagged_files else "✓ "
                confidence_badge = result.confidence.upper()
                lines.append(
                    f"  {flag}[{confidence_badge}] {result.file.filename}"
                    f"\n            {file_dur} → "
                    f"S{result.matched_episode.season:02d}E{result.matched_episode.episode:02d} "
                    f"({target_dur}) [Δ {delta_str}]"
                )

    lines.append("")

    # Flagged matches section
    if flagged_files:
        lines.append("🚩 FLAGGED FOR REVIEW")
        lines.append("-" * 80)

        # Collisions
        if collisions:
            lines.append("  COLLISION (multiple episodes match within 10s):")
            for result in collisions:
                lines.append(f"    • {result.file.filename} ({format_duration(result.file.duration_seconds)})")
                for i, (candidate, delta) in enumerate(result.all_candidates[:3], 1):
                    delta_str = format_duration(delta)
                    mark = "→ SELECTED" if i == 1 else "  alternative"
                    lines.append(
                        f"      {i}. S{candidate.season:02d}E{candidate.episode:02d} "
                        f"({candidate.title}) [Δ {delta_str}] {mark}"
                    )
            lines.append("")

        # Medium confidence
        if medium_conf:
            lines.append("  MEDIUM CONFIDENCE (30s < Δ ≤120s) — May need review:")
            for result in medium_conf:
                target_dur = format_duration(result.matched_episode.runtime_seconds)
                delta_str = format_duration(result.delta_seconds)
                lines.append(
                    f"    • {result.file.filename} → "
                    f"S{result.matched_episode.season:02d}E{result.matched_episode.episode:02d} "
                    f"[Δ {delta_str}] ({target_dur})"
                )
            lines.append("")

        # Low confidence
        if low_conf:
            lines.append("  LOW CONFIDENCE (Δ >120s) — Likely wrong, needs manual review:")
            for result in low_conf:
                target_dur = format_duration(result.matched_episode.runtime_seconds)
                delta_str = format_duration(result.delta_seconds)
                lines.append(
                    f"    • {result.file.filename} → "
                    f"S{result.matched_episode.season:02d}E{result.matched_episode.episode:02d} "
                    f"[Δ {delta_str}] ({target_dur})"
                )
            lines.append("")

        lines.append("    ACTION: Review flagged files and provide corrections")
        lines.append("")
    else:
        lines.append("✓ No flagged files — all matches are high confidence")
        lines.append("")

    # Unmatched files section
    if no_match:
        lines.append("❌ UNMATCHED FILES")
        lines.append("-" * 80)
        for result in no_match:
            lines.append(f"  {result.file.filename} ({format_duration(result.file.duration_seconds)})")
        lines.append("")
    else:
        lines.append("✓ All files matched")
        lines.append("")

    # Summary
    lines.append("SUMMARY")
    lines.append("-" * 80)
    lines.append(f"  Total files: {len(results)}")
    lines.append(f"  ✓ HIGH confidence (Δ ≤30s): {len(high_conf)}")
    lines.append(f"  ⚠ MEDIUM confidence (30s < Δ ≤120s): {len(medium_conf)}")
    lines.append(f"  ⚠ LOW confidence (Δ >120s): {len(low_conf)}")
    lines.append(f"  ❌ Unmatched: {len(no_match)}")
    lines.append(f"  🚩 Collisions (multiple matches): {len(collisions)}")

    if no_match or flagged_files:
        lines.append("")
        lines.append("⚠️ ACTION REQUIRED: Review flagged/unmatched files")
        lines.append("   Provide corrections via: 'file.mkv -> S##E## (title)'")
    else:
        lines.append("")
        lines.append("✓ All matches verified — ready to apply")

    lines.append("=" * 80)

    return "\n".join(lines)


def save_report(
    report_text: str,
    show: str,
    season: int,
    disk: int,
    base_path: Path = None,
) -> Path:
    """
    Save report to file.

    Returns:
        Path to saved report
    """
    if base_path is None:
        base_path = Path(__file__).parent / show

    reports_dir = base_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_path = reports_dir / f"S{season:02d}D{disk:02d}_report.txt"
    report_path.write_text(report_text, encoding='utf-8')

    log.info(f"Report saved to: {report_path}")
    return report_path


def generate_mapping_json(
    results: List[MatchResult],
    show: str,
) -> Dict[str, str]:
    """
    Generate JSON mapping for use by rename tool.

    Format: {
        "title_t00.mkv": "[Show] - S01E01 - [Title].mkv",
        ...
    }
    """
    mapping = {}

    for result in results:
        if result.matched_episode:
            ep = result.matched_episode
            filename = result.file.filename
            new_name = (
                f"{show} - S{ep.season:02d}E{ep.episode:02d} - {ep.title}.mkv"
            )
            mapping[filename] = new_name

    return mapping


def save_mapping_json(
    mapping: Dict[str, str],
    show: str,
    season: int,
    disk: int,
    base_path: Path = None,
) -> Path:
    """
    Save mapping JSON to file.

    Returns:
        Path to saved mapping
    """
    if base_path is None:
        base_path = Path(__file__).parent / show

    mappings_dir = base_path / "mappings"
    mappings_dir.mkdir(parents=True, exist_ok=True)

    mapping_path = mappings_dir / f"S{season:02d}D{disk:02d}.json"
    mapping_path.write_text(json.dumps(mapping, indent=2), encoding='utf-8')

    log.info(f"Mapping saved to: {mapping_path}")
    return mapping_path
