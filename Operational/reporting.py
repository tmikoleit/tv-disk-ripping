"""
Generate reports from matching results.

Integrates greedy matching algorithm with collision detection to highlight
episodes matched by multiple files (hard errors requiring user correction).
"""

from typing import List, Dict
from pathlib import Path
import json
import logging

from matcher import MatchResult, EpisodeTarget, match_files_greedy

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


def detect_clustering_ambiguities(results: List[MatchResult], threshold_seconds: int = 30) -> Dict[str, List[tuple]]:
    """
    Detect when multiple episodes have identical runtimes and multiple files could be permutations of them.

    Returns dict mapping cluster_key -> list of (result, candidate_episodes)
    """
    from collections import defaultdict

    # Get all unique episodes and their runtimes from all_candidates
    all_episodes_seen = {}
    for result in results:
        for candidate, _ in result.all_candidates:
            if candidate.episode not in all_episodes_seen:
                all_episodes_seen[candidate.episode] = candidate

    # Group episodes by runtime
    episode_runtimes = defaultdict(list)
    for episode_num, ep in all_episodes_seen.items():
        runtime_key = ep.runtime_seconds
        episode_runtimes[runtime_key].append(ep)

    # Find runtimes with multiple different episodes
    clusters = {}
    for runtime, episodes in episode_runtimes.items():
        unique_episodes = list({ep.episode: ep for ep in episodes}.values())
        if len(unique_episodes) > 1:
            cluster_key = f"E{'-'.join(str(e.episode).zfill(2) for e in sorted(unique_episodes, key=lambda x: x.episode))}"
            clusters[cluster_key] = unique_episodes

    # Find files that could match multiple episodes in same cluster
    clustering_issues = {}
    for cluster_key, cluster_episodes in clusters.items():
        files_in_cluster = []
        for result in results:
            # Check if this file could match ANY episode in the cluster within threshold
            candidates_in_cluster = [
                ep for ep in cluster_episodes
                if abs(result.file.duration_seconds - ep.runtime_seconds) <= threshold_seconds
            ]
            if len(candidates_in_cluster) > 1:
                files_in_cluster.append((result, candidates_in_cluster))

        if len(files_in_cluster) > 1:
            clustering_issues[cluster_key] = files_in_cluster

    return clustering_issues


def generate_text_report(
    results: List[MatchResult],
    show: str,
    season: int,
    disk: int,
    collisions: Dict[EpisodeTarget, List] = None,
) -> str:
    """
    Generate a human-readable text report with collision detection.

    Returns a formatted string report with:
    - COLLISIONS section (HARD ERROR — episodes matched by multiple files)
    - All matched files with confidence levels
    - Flagged files (medium/low confidence, unmatched)
    - Summary statistics

    Args:
        results: List of MatchResult objects from greedy matching
        show: Show name
        season: Season number
        disk: Disk number
        collisions: Dict of EpisodeTarget → List[RippedFile] from match_files_greedy()
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

    # Get collision files for highlighting
    collision_files = set()
    if collisions:
        for ep, files in collisions.items():
            for f in files:
                collision_files.add(f.filename)

    # Detect clustering: episodes with identical runtimes where files could be permutations
    clustering_issues = detect_clustering_ambiguities(results, threshold_seconds=30)

    # Detect ambiguities: collisions (multiple matches <5s delta)
    # ONLY flag when file durations were actually measured (<= 0 means proxy from TMDb)
    # When using proxy durations, don't flag false ambiguities from similar TMDb runtimes
    duration_collisions = [
        r for r in results
        if r.confidence != "no_match"
        and r.delta_seconds > 0  # Only flag if actual file duration was measured
        and len(r.all_candidates) > 1
        and r.all_candidates[0][1] <= 5
        and any(c[1] <= 5 for c in r.all_candidates[1:])
    ]

    # Flagged files: collisions + medium/low confidence (as list, avoiding set issues)
    flagged_files = duration_collisions + medium_conf + low_conf

    # COLLISIONS section (hard error — episode ← multiple files)
    if collisions:
        lines.append("❌ COLLISIONS — HARD ERROR")
        lines.append("-" * 80)
        lines.append("Multiple files matched to the same episode. This must be corrected:")
        lines.append("")
        for ep, files in collisions.items():
            lines.append(f"  EPISODE MATCHED BY {len(files)} FILES:")
            lines.append(f"    S{ep.season:02d}E{ep.episode:02d} - {ep.title}")
            for f in files:
                # Find the result for this file
                result = next((r for r in results if r.file.filename == f.filename), None)
                if result:
                    delta_str = format_duration(result.delta_seconds)
                    lines.append(f"      • {f.filename} [Δ {delta_str}]")
            lines.append("")
        lines.append("    ACTION REQUIRED: Provide corrections via --correct flag")
        lines.append("")
    lines.append("")

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

                # Highlight collision files, flagged files, and greedy matches
                if result.file.filename in collision_files:
                    flag = "❌"  # Collision
                elif result in flagged_files:
                    flag = "⚠️ "  # Other flags
                else:
                    flag = "✓ "  # OK

                confidence_badge = result.confidence.upper()
                greedy_mark = " [GREEDY]" if not result.collision and result.delta_seconds == 0 and "E" in str(result.matched_episode) else ""
                lines.append(
                    f"  {flag}[{confidence_badge}] {result.file.filename}{greedy_mark}"
                    f"\n            {file_dur} → "
                    f"S{result.matched_episode.season:02d}E{result.matched_episode.episode:02d} "
                    f"({target_dur}) [Δ {delta_str}]"
                )

    lines.append("")

    # Clustering section - episodes with identical runtimes where files could be permutations
    if clustering_issues:
        lines.append("🔀 POTENTIAL PERMUTATION CLUSTERS")
        lines.append("-" * 80)
        lines.append("  Episodes with identical runtimes where files could be swapped:")
        lines.append("")
        for cluster_key, files_in_cluster in clustering_issues.items():
            episode_nums = [r.matched_episode.episode for r, _ in files_in_cluster]
            episode_nums = sorted(set(episode_nums))
            lines.append(f"  CLUSTER {cluster_key}:")
            lines.append(f"    These {len(files_in_cluster)} files could be any permutation of episodes: {', '.join(f'E{e:02d}' for e in episode_nums)}")
            lines.append("")
            for result, candidates in files_in_cluster:
                lines.append(f"    • {result.file.filename} ({format_duration(result.file.duration_seconds)})")
                for i, ep in enumerate(sorted(candidates, key=lambda x: x.episode), 1):
                    delta = abs(result.file.duration_seconds - ep.runtime_seconds)
                    mark = "← SELECTED" if result.matched_episode == ep else ""
                    lines.append(
                        f"      {i}. S{ep.season:02d}E{ep.episode:02d} ({ep.title:30s}) [Δ {format_duration(delta)}] {mark}"
                    )
            lines.append("")
        lines.append("    ACTION: Verify these files together and reorder them if needed")
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
    lines.append(f"  ❌ COLLISIONS (episode ← multiple files): {len(collisions) if collisions else 0}")
    lines.append(f"  🚩 Duration ambiguities (multiple matches <5s): {len(duration_collisions)}")

    if collisions:
        lines.append("")
        lines.append("❌ HARD ERROR: Collisions must be corrected before proceeding")
        lines.append("   Provide corrections via: --correct 'file.mkv -> S##E##'")
    elif no_match or flagged_files:
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
