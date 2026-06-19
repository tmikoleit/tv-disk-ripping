"""
Interactive correction workflow for disk ripping matches.

Allows user to provide corrections in format:
  filename.mkv -> S##E## (title)

Example:
  title_t00.mkv -> S01E14 (Interpretive Dance)
"""

import re
from typing import List, Dict, Optional, Tuple
from matcher import MatchResult, EpisodeTarget


def parse_correction(correction_str: str) -> Optional[Tuple[str, int, int]]:
    """
    Parse user correction string.

    Format: "filename.mkv -> S##E## (optional title)"
    Returns: (filename, season, episode) or None if invalid

    Examples:
        "title_t00.mkv -> S01E14"
        "title_t00.mkv -> S01E14 (Interpretive Dance)"
    """
    pattern = r'^(.+\.mkv)\s*->\s*S(\d+)E(\d+)'
    match = re.match(pattern, correction_str.strip())
    if match:
        filename = match.group(1).strip()
        season = int(match.group(2))
        episode = int(match.group(3))
        return (filename, season, episode)
    return None


def apply_correction(
    results: List[MatchResult],
    filename: str,
    target_season: int,
    target_episode: int,
    all_episodes: Dict[int, EpisodeTarget],
) -> Tuple[bool, str]:
    """
    Apply a correction to a specific file.

    Args:
        results: List of match results
        filename: File to correct
        target_season: Target season number
        target_episode: Target episode number
        all_episodes: Dict mapping episode number to EpisodeTarget

    Returns:
        (success: bool, message: str)
    """
    result = None
    for r in results:
        if r.file.filename == filename:
            result = r
            break

    if not result:
        return False, f"File not found: {filename}"

    # Find target episode
    ep_key = (target_season, target_episode)
    target_ep = None
    for candidate, _ in result.all_candidates:
        if candidate.season == target_season and candidate.episode == target_episode:
            target_ep = candidate
            break

    if not target_ep:
        return False, f"Episode not in candidates for {filename}: S{target_season:02d}E{target_episode:02d}"

    # Update match
    old_match = f"S{result.matched_episode.season:02d}E{result.matched_episode.episode:02d}"
    result.matched_episode = target_ep
    result.delta_seconds = abs(result.file.duration_seconds - target_ep.runtime_seconds)

    # Update confidence based on new delta
    if result.delta_seconds <= 30:
        result.confidence = "high"
    elif result.delta_seconds <= 120:
        result.confidence = "medium"
    else:
        result.confidence = "low"

    new_match = f"S{target_ep.season:02d}E{target_ep.episode:02d}"
    return True, f"✓ {filename}: {old_match} → {new_match}"


def apply_corrections_interactive(results: List[MatchResult], corrections: List[str]) -> Dict[str, str]:
    """
    Apply multiple user corrections.

    Args:
        results: List of match results
        corrections: List of correction strings like "title_t00.mkv -> S01E14"

    Returns:
        Dict mapping filename to result message
    """
    messages = {}
    all_candidates = {}
    for result in results:
        for candidate, _ in result.all_candidates:
            all_candidates[(candidate.season, candidate.episode)] = candidate

    for correction_str in corrections:
        parsed = parse_correction(correction_str)
        if not parsed:
            messages[correction_str] = f"❌ Invalid format: {correction_str}"
            continue

        filename, season, episode = parsed
        success, msg = apply_correction(results, filename, season, episode, all_candidates)
        messages[correction_str] = msg

    return messages
