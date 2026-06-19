"""
Scan MKV files and extract duration information.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple

log = logging.getLogger(__name__)


def get_mkv_duration_ffprobe(filepath: Path) -> Optional[int]:
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
            log.debug(f"ffprobe failed for {filepath.name}")
            return None

    except FileNotFoundError:
        log.debug("ffprobe not available in PATH")
        return None
    except subprocess.TimeoutExpired:
        log.debug(f"ffprobe timeout for {filepath.name}")
        return None
    except Exception as e:
        log.debug(f"Error with ffprobe: {e}")
        return None


def get_mkv_duration_pymediainfo(filepath: Path) -> Optional[int]:
    """
    Extract duration using pymediainfo library.

    Returns:
        Duration in seconds, or None if extraction failed
    """
    try:
        import mediainfo
        info = mediainfo.MediaInfo.parse(str(filepath))
        for track in info.tracks:
            if track.track_type == "General":
                duration_ms = track.duration
                if duration_ms:
                    return int(duration_ms / 1000)
        return None
    except ImportError:
        log.debug("pymediainfo not installed")
        return None
    except Exception as e:
        log.debug(f"Error with pymediainfo: {e}")
        return None


def get_mkv_duration(filepath: Path) -> Optional[int]:
    """
    Extract duration from MKV file.

    Tries multiple methods:
    1. ffprobe (fastest if available)
    2. pymediainfo (requires MediaInfo binary)

    Returns:
        Duration in seconds, or None if extraction failed
    """
    # Try ffprobe first
    duration = get_mkv_duration_ffprobe(filepath)
    if duration is not None:
        return duration

    # Try pymediainfo
    duration = get_mkv_duration_pymediainfo(filepath)
    if duration is not None:
        return duration

    log.warning(f"Could not extract duration: {filepath.name}")
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

    failed = 0
    for mkv_file in mkv_files:
        duration = get_mkv_duration(mkv_file)
        if duration is not None:
            files.append((mkv_file.name, duration))
            log.debug(f"{mkv_file.name}: {duration}s")
        else:
            failed += 1

    if failed > 0:
        log.warning(f"⚠️ Could not extract duration for {failed}/{len(mkv_files)} files")
        log.warning(f"   Install ffmpeg: choco install ffmpeg -y")
        log.warning(f"   Or install mediainfo: choco install mediainfo-cli -y")

    return files
