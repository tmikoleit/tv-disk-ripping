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
    - Ambiguous matches (if any)
    - Unmatched files (if any)
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
    ambiguous = [r for r in results if len(r.all_candidates) > 1 and r.all_candidates[0][1] <= 10]

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

                confidence_badge = result.confidence.upper()
                lines.append(
                    f"  [{confidence_badge}] {result.file.filename}"
                    f"\n            Duration: {file_dur} → "
                    f"S{result.matched_episode.season:02d}E{result.matched_episode.episode:02d} "
                    f"({target_dur}) [delta: {delta_str}]"
                )

    lines.append("")

    # Ambiguous matches section
    if ambiguous:
        lines.append("⚠️  AMBIGUOUS MATCHES")
        lines.append("-" * 80)
        for result in ambiguous:
            lines.append(f"  File: {result.file.filename} ({format_duration(result.file.duration_seconds)})")

            # Show all candidates within 10 seconds
            for candidate, delta in result.all_candidates[:3]:
                delta_str = format_duration(delta)
                lines.append(
                    f"    → Could be S{candidate.season:02d}E{candidate.episode:02d} "
                    f"({candidate.title}) [delta: {delta_str}]"
                )

            lines.append("    ACTION: Manual review needed")
            lines.append("")
    else:
        lines.append("✓ No ambiguous matches detected")
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
    lines.append(f"  ✓ HIGH confidence (≤30s): {len(high_conf)}")
    lines.append(f"  ⚠ MEDIUM confidence (≤120s): {len(medium_conf)}")
    lines.append(f"  ⚠ LOW confidence (>120s): {len(low_conf)}")
    lines.append(f"  ❌ Unmatched: {len(no_match)}")
    lines.append(f"  ⚠ Ambiguous: {len(ambiguous)}")

    if no_match or ambiguous:
        lines.append("")
        lines.append("ACTION REQUIRED: Review unmatched and ambiguous files before applying mapping")
    else:
        lines.append("")
        lines.append("✓ Ready to apply mapping")

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
    report_path.write_text(report_text)

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
    mapping_path.write_text(json.dumps(mapping, indent=2))

    log.info(f"Mapping saved to: {mapping_path}")
    return mapping_path
