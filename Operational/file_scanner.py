"""
Scan MKV files and extract duration information.
"""

import logging
import subprocess
import json
from pathlib import Path
from typing import Optional, List, Tuple

log = logging.getLogger(__name__)


def get_mkv_duration(filepath: Path) -> Optional[int]:
    """
    Extract duration from MKV file using ffprobe.

    Returns:
        Duration in seconds, or None if extraction failed
    """
    try:
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1:nokey_wrappers=1',
                str(filepath)
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            duration_str = result.stdout.strip()
            return int(float(duration_str))
        else:
            log.warning(f"ffprobe failed for {filepath.name}: {result.stderr}")
            return None

    except FileNotFoundError:
        log.error("ffprobe not found. Install: pip install ffprobe-python or brew install ffmpeg")
        return None
    except subprocess.TimeoutExpired:
        log.error(f"ffprobe timeout for {filepath.name}")
        return None
    except Exception as e:
        log.error(f"Error extracting duration from {filepath.name}: {e}")
        return None


def scan_disk_folder(disk_path: Path) -> List[Tuple[str, int]]:
    """
    Scan a Disk folder and extract all MKV file durations.

    Args:
        disk_path: Path to Disk N folder

    Returns:
        List of (filename, duration_seconds) tuples
    """
    if not disk_path.exists():
        log.warning(f"Disk folder not found: {disk_path}")
        return []

    files = []
    mkv_files = sorted(disk_path.glob("*.mkv"))

    if not mkv_files:
        log.warning(f"No MKV files found in {disk_path}")
        return []

    log.info(f"Scanning {len(mkv_files)} MKV files...")

    for mkv_file in mkv_files:
        duration = get_mkv_duration(mkv_file)
        if duration is not None:
            files.append((mkv_file.name, duration))
            log.debug(f"{mkv_file.name}: {duration}s")

    return files
