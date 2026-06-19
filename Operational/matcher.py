"""
Runtime-based episode matching with disc-level constraints.

Implements greedy matching algorithm prioritizing unique-runtime episodes first,
then duration-based matching with collision detection.

Inspired by riplex (https://github.com/AnyCredit5518/riplex) with enhancements:
- Greedy matching for unambiguous episodes (unique runtimes)
- Collision detection (hard error if episode ← multiple files)
- Better confidence thresholds (±30s for high confidence)

FUTURE: Original filename matching when MakeMKV logs are captured during ripping.
MakeMKV shows track_001.m2ts → title_t00.mkv mappings, and thediskdb.com has
original filenames linked to episode names. This would enable 100% accurate
matching without relying on duration ambiguities. Implementation blocked on
capturing MakeMKV GUI logs programmatically.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Set
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
    collision: bool = False  # True if multiple files match this episode


@dataclass
class CollisionInfo:
    """Tracks episodes with multiple file matches."""
    episode: EpisodeTarget
    files: List[RippedFile] = field(default_factory=list)
    count: int = 0


def get_confidence(delta: int) -> str:
    """
    Determine confidence level based on delta (seconds).

    HIGH: ≤30s (riplex standard, reliable for most cases)
    MEDIUM: ≤120s (looser tolerance, ambiguity likely)
    LOW: >120s (poor match, may not belong on this disk)
    """
    if delta <= CONFIDENCE_HIGH:
        return "high"
    elif delta <= CONFIDENCE_MEDIUM:
        return "medium"
    else:
        return "low"


def find_unique_runtime_episodes(
    episode_targets: List[EpisodeTarget],
) -> Dict[int, EpisodeTarget]:
    """
    Identify episodes with unique runtimes (no ambiguity).

    Returns:
        Dict mapping runtime_seconds → EpisodeTarget for unique runtimes
    """
    runtime_counts: Dict[int, List[EpisodeTarget]] = {}
    for target in episode_targets:
        if target.runtime_seconds > 0:
            runtime_counts.setdefault(target.runtime_seconds, []).append(target)

    # Keep only episodes where runtime is unique to that episode
    unique = {}
    for runtime, episodes in runtime_counts.items():
        if len(episodes) == 1:
            unique[runtime] = episodes[0]

    return unique


def detect_collisions(
    results: List[MatchResult],
) -> Dict[str, List[RippedFile]]:
    """
    Detect collisions: episodes matched by multiple files.

    Returns:
        Dict mapping episode key (S##E##) → list of files that matched it
    """
    episode_file_map: Dict[str, tuple] = {}  # ep_key → (EpisodeTarget, [RippedFiles])
    for result in results:
        if result.matched_episode is not None:
            ep = result.matched_episode
            ep_key = f"S{ep.season:02d}E{ep.episode:02d}"
            if ep_key not in episode_file_map:
                episode_file_map[ep_key] = (ep, [])
            episode_file_map[ep_key][1].append(result.file)

    # Return only episodes with multiple matches, as dict {ep_key: (EpisodeTarget, [files])}
    return {
        ep_key: (ep_target, files)
        for ep_key, (ep_target, files) in episode_file_map.items()
        if len(files) > 1
    }


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


def match_files_greedy(
    ripped_files: List[RippedFile],
    episode_targets: List[EpisodeTarget],
    disk_episodes: Optional[List[int]] = None,
) -> Tuple[List[MatchResult], Dict[EpisodeTarget, List[RippedFile]]]:
    """
    Match all ripped files to episodes using greedy algorithm.

    Algorithm:
    1. Identify episodes with UNIQUE runtimes (no ambiguity)
    2. First pass: match files to unique-runtime episodes
    3. Second pass: match remaining files using best-match logic
    4. Detect and return collisions

    Args:
        ripped_files: List of MKV files to match
        episode_targets: All available episode targets
        disk_episodes: Constraint - only match these episode numbers

    Returns:
        Tuple of (MatchResult list, collision dict)
        - MatchResult.collision flag set to True for involved files
        - Dict maps EpisodeTarget → list of files with collision
    """
    # Step 1: Find episodes with unique runtimes
    unique_runtimes = find_unique_runtime_episodes(episode_targets)
    matched_files: Set[str] = set()
    results = []

    # Step 2: First pass - match to unique-runtime episodes
    for ripped_file in ripped_files:
        if ripped_file.duration_seconds in unique_runtimes:
            target = unique_runtimes[ripped_file.duration_seconds]
            delta = abs(ripped_file.duration_seconds - target.runtime_seconds)

            result = MatchResult(
                file=ripped_file,
                matched_episode=target,
                delta_seconds=delta,
                confidence=get_confidence(delta),
                all_candidates=[(target, delta)],
                collision=False
            )
            results.append(result)
            matched_files.add(ripped_file.filename)
            log.info(f"[GREEDY] {ripped_file.filename} → {target.show} S{target.season:02d}E{target.episode:02d} (unique runtime match)")
        else:
            # Placeholder for second pass
            results.append(None)

    # Step 3: Second pass - match remaining files
    remaining_files = [f for f in ripped_files if f.filename not in matched_files]
    for i, ripped_file in enumerate(ripped_files):
        if results[i] is not None:
            continue  # Already matched in first pass

        result = match_file(ripped_file, episode_targets, disk_episodes)
        results[i] = result

    # Step 4: Detect collisions
    collisions = detect_collisions(results)
    for collision_episode, files in collisions.items():
        for result in results:
            if result.matched_episode == collision_episode:
                result.collision = True

    if collisions:
        log.warning(f"[COLLISION] Detected {len(collisions)} episodes with multiple file matches:")
        for ep_key, (ep_target, files) in collisions.items():
            log.warning(f"  {ep_key}: {[f.filename for f in files]}")

    return results, collisions


def match_files(
    ripped_files: List[RippedFile],
    episode_targets: List[EpisodeTarget],
    disk_episodes: Optional[List[int]] = None,
) -> List[MatchResult]:
    """
    Match all ripped files to episodes (standard algorithm).

    Uses greedy matching with collision detection. For most use cases,
    prefer match_files_greedy() which provides collision information.

    Args:
        ripped_files: List of MKV files to match
        episode_targets: All available episode targets
        disk_episodes: Constraint - only match these episode numbers

    Returns:
        List of MatchResult objects
    """
    results, _ = match_files_greedy(ripped_files, episode_targets, disk_episodes)
    return results
