"""
Organize ripped and renamed files into Plex-ready folder structure.

Moves renamed files from working directory to completed folder:
  D:\Disk Ripping\[Show]\Season [N]\Disk [N]\[renamed files]
    ↓
  D:\Disk Ripping\Completed\[Show] (YYYY)\Season [N]\[renamed files]

Where YYYY is the show's premiere year from disc_data or TMDb.
"""

from pathlib import Path
from typing import Optional, Dict, List
import logging
import shutil

from disc_lookup import get_show_premiere_year
from config import BASE_DIR

log = logging.getLogger(__name__)


def get_completed_path(
    show: str,
    season: int,
    premiere_year: Optional[int] = None,
    base_path: Path = None,
) -> Path:
    """
    Get path for completed files.

    Creates folder structure: Completed/[Show] (YYYY)/Season [N]/

    Args:
        show: Show name
        season: Season number
        premiere_year: Year show premiered (if None, will be looked up)
        base_path: Base directory (default: D:\Disk Ripping)

    Returns:
        Path to completed season folder
    """
    if base_path is None:
        base_path = BASE_DIR

    # Get premiere year if not provided
    if premiere_year is None:
        premiere_year = get_show_premiere_year(show)
        if premiere_year is None:
            log.warning(f"Could not determine premiere year for {show}, using 0000")
            premiere_year = 0

    # Create folder: Completed/[Show] (YYYY)/Season [N]/
    show_folder = f"{show} ({premiere_year})"
    season_folder = f"Season {season}"

    completed_path = base_path / "Completed" / show_folder / season_folder
    return completed_path


def move_to_completed(
    show: str,
    season: int,
    disk: int,
    premiere_year: Optional[int] = None,
    base_path: Path = None,
    dry_run: bool = False,
) -> Dict[str, any]:
    """
    Move renamed files from working directory to completed folder.

    Args:
        show: Show name
        season: Season number
        disk: Disk number
        premiere_year: Year show premiered (if None, will be looked up)
        base_path: Base directory (default: D:\Disk Ripping)
        dry_run: If True, don't actually move files

    Returns:
        Dict with results: {
            'completed_path': Path,
            'files_moved': int,
            'files_failed': int,
            'removed_empty_dirs': List[Path]
        }
    """
    if base_path is None:
        base_path = BASE_DIR

    # Get paths
    working_disk_path = (
        base_path / show / f"Season {season}" / f"Disk {disk}"
    )
    completed_path = get_completed_path(show, season, premiere_year, base_path)

    result = {
        'completed_path': completed_path,
        'files_moved': 0,
        'files_failed': 0,
        'removed_empty_dirs': []
    }

    # Check working directory exists
    if not working_disk_path.exists():
        log.error(f"Working directory not found: {working_disk_path}")
        return result

    # Create completed directory
    if not dry_run:
        completed_path.mkdir(parents=True, exist_ok=True)

    # Find all .mkv files in working directory
    mkv_files = list(working_disk_path.glob("*.mkv"))

    if not mkv_files:
        log.warning(f"No .mkv files found in {working_disk_path}")
        return result

    # Move files
    for mkv_file in mkv_files:
        dest_file = completed_path / mkv_file.name

        try:
            if dry_run:
                log.info(f"[DRY RUN] Would move: {mkv_file.name}")
            else:
                shutil.move(str(mkv_file), str(dest_file))
                log.info(f"✓ Moved: {mkv_file.name}")

            result['files_moved'] += 1

        except Exception as e:
            log.error(f"❌ Failed to move {mkv_file.name}: {e}")
            result['files_failed'] += 1

    # Clean up empty source directories
    if not dry_run:
        dirs_to_remove = [
            working_disk_path,  # Disk [N] folder
            working_disk_path.parent,  # Season [N] folder (if empty)
            working_disk_path.parent.parent,  # Show folder (if empty)
        ]

        for dir_path in dirs_to_remove:
            try:
                # Only remove if empty
                if dir_path.exists() and not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    log.info(f"✓ Removed empty dir: {dir_path.name}")
                    result['removed_empty_dirs'].append(dir_path)
            except Exception as e:
                # Don't fail if we can't remove (might have other content)
                pass

    return result


def organize_season(
    show: str,
    season: int,
    premiere_year: Optional[int] = None,
    base_path: Path = None,
    dry_run: bool = False,
) -> Dict[str, any]:
    """
    Move all disks of a season to completed folder.

    Finds all Disk [N] folders in Season [season] and moves them to completed.

    Args:
        show: Show name
        season: Season number
        premiere_year: Year show premiered (if None, will be looked up)
        base_path: Base directory (default: D:\Disk Ripping)
        dry_run: If True, don't actually move files

    Returns:
        Dict with aggregated results across all disks
    """
    if base_path is None:
        base_path = BASE_DIR

    season_path = base_path / show / f"Season {season}"

    if not season_path.exists():
        log.error(f"Season directory not found: {season_path}")
        return {'files_moved': 0, 'files_failed': 0, 'disks_processed': 0}

    # Find all Disk folders
    disk_folders = sorted([d for d in season_path.glob("Disk *") if d.is_dir()])

    if not disk_folders:
        log.warning(f"No disk folders found in {season_path}")
        return {'files_moved': 0, 'files_failed': 0, 'disks_processed': 0}

    # Aggregate results
    total_moved = 0
    total_failed = 0
    all_removed_dirs = []

    for disk_path in disk_folders:
        try:
            disk_num = int(disk_path.name.split()[-1])
        except (ValueError, IndexError):
            log.warning(f"Could not parse disk number from {disk_path.name}")
            continue

        log.info(f"\nProcessing {show} S{season:02d}D{disk_num}...")

        result = move_to_completed(
            show, season, disk_num, premiere_year, base_path, dry_run
        )

        total_moved += result['files_moved']
        total_failed += result['files_failed']
        all_removed_dirs.extend(result['removed_empty_dirs'])

    return {
        'files_moved': total_moved,
        'files_failed': total_failed,
        'disks_processed': len(disk_folders),
        'removed_empty_dirs': all_removed_dirs
    }
