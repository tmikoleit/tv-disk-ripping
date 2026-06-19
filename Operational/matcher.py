"""
Runtime-based episode matching with disc-level constraints.

Implements riplex-style matching with configurable confidence thresholds.
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
import logging

from config import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    MAX_DELTA,
)

log = logging.getLogger(__name__)


@dataclass
class EpisodeTarget:
    """Target episode for matching."""
    show: str
    season: int
    episode: int
    title: str
    runtime_seconds: int


@dataclass
class RippedFile:
    """Ripped MKV file metadata."""
    filename: str
    duration_seconds: int
    file_size_gb: float = 0.0


@dataclass
class MatchResult:
    """Result of matching a ripped file to an episode."""
    file: RippedFile
    matched_episode: Optional[EpisodeTarget]
    delta_seconds: int
    confidence: str  # "high", "medium", "low", "no_match"
    all_candidates: List[Tuple[EpisodeTarget, int]]  # All possible matches within threshold


def get_confidence(delta: int) -> str:
    """
    Determine confidence level based on delta (seconds).

    HIGH: ≤30s
    MEDIUM: ≤120s
    LOW: >120s
    """
    if delta <= CONFIDENCE_HIGH:
        return "high"
    elif delta <= CONFIDENCE_MEDIUM:
        return "medium"
    else:
        return "low"


def match_file(
    ripped_file: RippedFile,
    episode_targets: List[EpisodeTarget],
    disk_episodes: Optional[List[int]] = None,
) -> MatchResult:
    """
    Match a single ripped file to episodes.

    Args:
        ripped_file: The MKV file to match
        episode_targets: All available episode targets
        disk_episodes: Constraint - only match these episode numbers (if provided)

    Returns:
        MatchResult with best match and all candidates within threshold
    """

    best_match = None
    best_delta = float('inf')
    best_size_diff = float('inf')
    candidates: List[Tuple[EpisodeTarget, int]] = []

    for target in episode_targets:
        # Apply disk constraint if provided
        if disk_episodes is not None and target.episode not in disk_episodes:
            continue

        if target.runtime_seconds <= 0:
            continue

        delta = abs(ripped_file.duration_seconds - target.runtime_seconds)

        # Track all candidates within threshold for ambiguity detection
        if delta <= MAX_DELTA:
            candidates.append((target, delta))

        # Track best match (prefer tight duration match, break ties with file size)
        if delta < best_delta:
            best_delta = delta
            best_match = target
            best_size_diff = float('inf')
        elif delta == best_delta and ripped_file.file_size_gb > 0:
            # If duration delta is identical, use file size as tiebreaker
            # Larger episodes typically have larger files
            size_diff = abs(ripped_file.file_size_gb - (target.runtime_seconds / 3600))
            if size_diff < best_size_diff:
                best_size_diff = size_diff
                best_match = target

    # Sort candidates by delta for reporting
    candidates.sort(key=lambda x: x[1])

    if best_match is None:
        return MatchResult(
            file=ripped_file,
            matched_episode=None,
            delta_seconds=-1,
            confidence="no_match",
            all_candidates=[]
        )

    return MatchResult(
        file=ripped_file,
        matched_episode=best_match,
        delta_seconds=best_delta,
        confidence=get_confidence(best_delta),
        all_candidates=candidates
    )


def match_files(
    ripped_files: List[RippedFile],
    episode_targets: List[EpisodeTarget],
    disk_episodes: Optional[List[int]] = None,
) -> List[MatchResult]:
    """
    Match all ripped files to episodes.

    Args:
        ripped_files: List of MKV files to match
        episode_targets: All available episode targets
        disk_episodes: Constraint - only match these episode numbers

    Returns:
        List of MatchResult objects
    """
    results = []
    for ripped_file in ripped_files:
        result = match_file(ripped_file, episode_targets, disk_episodes)
        results.append(result)

    return results
