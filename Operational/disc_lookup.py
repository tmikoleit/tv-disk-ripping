"""
Disc metadata lookup from dvdcompare.net and TMDb.
"""

import logging
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
import requests
from pathlib import Path
import json
import time
from urllib.parse import quote

from config import TMDB_API_KEY, DVDCOMPARE_CACHE_TTL, BASE_DIR

log = logging.getLogger(__name__)


@dataclass
class DiscInfo:
    """Information about a physical disc."""
    show: str
    season: int
    disk: int
    episodes: List[int]  # Episode numbers on this disk
    release_region: Optional[str] = None
    source: str = "dvdcompare"  # Track where info came from


@dataclass
class EpisodeMeta:
    """Episode metadata from TMDb."""
    season: int
    episode: int
    title: str
    runtime_seconds: int
    air_date: Optional[str] = None


def _get_cache_dir() -> Path:
    """Get or create cache directory."""
    cache_dir = BASE_DIR / ".cache" / "dvdcompare"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_key(show: str, season: int, disk: int) -> str:
    """Generate cache key for disc lookup."""
    return f"{show.lower().replace(' ', '_')}_{season:02d}_{disk:02d}"


def _load_from_cache(cache_key: str) -> Optional[DiscInfo]:
    """Load disc info from cache if available and fresh."""
    cache_dir = _get_cache_dir()
    cache_file = cache_dir / f"{cache_key}.json"

    if not cache_file.exists():
        return None

    try:
        mtime = cache_file.stat().st_mtime
        age = time.time() - mtime

        if age > DVDCOMPARE_CACHE_TTL:
            log.debug(f"Cache expired for {cache_key}")
            return None

        data = json.loads(cache_file.read_text())
        log.debug(f"Loaded from cache: {cache_key}")
        return DiscInfo(**data)

    except Exception as e:
        log.warning(f"Error reading cache: {e}")
        return None


def _save_to_cache(cache_key: str, info: DiscInfo) -> None:
    """Save disc info to cache."""
    cache_dir = _get_cache_dir()
    cache_file = cache_dir / f"{cache_key}.json"

    try:
        cache_file.write_text(json.dumps({
            "show": info.show,
            "season": info.season,
            "disk": info.disk,
            "episodes": info.episodes,
            "release_region": info.release_region,
            "source": info.source,
        }, indent=2))
        log.debug(f"Cached: {cache_key}")
    except Exception as e:
        log.warning(f"Error writing cache: {e}")


def _load_disc_database() -> dict:
    """Load disc episode mapping and metadata from local file."""
    db_file = Path(__file__).parent / "disc_data.json"
    if db_file.exists():
        try:
            data = json.loads(db_file.read_text())
            # Convert new metadata format to old for backward compatibility
            for show_key, seasons in data.items():
                for season_key, disks in seasons.items():
                    for disk_key, disk_data in disks.items():
                        if isinstance(disk_data, dict) and "episodes" in disk_data:
                            # New format: {episodes: [...], metadata: {...}}
                            pass  # Leave as-is for processing below
                        elif isinstance(disk_data, list):
                            # Old format: just episode list
                            data[show_key][season_key][disk_key] = {
                                "episodes": disk_data,
                                "metadata": {}
                            }
            return data
        except Exception as e:
            log.debug(f"Error reading disc_data.json: {e}")
    return {}


def get_disc_episodes_from_dvdcompare(
    show: str,
    season: int,
    disk: int,
) -> Optional[DiscInfo]:
    """
    Look up which episodes are on this disk.

    Tries methods in order:
    1. Local cache (24-hour TTL)
    2. dvdcompare-scraper library (if installed)
    3. Local disc_data.json database
    4. Manual user input (TODO)

    Args:
        show: Show name
        season: Season number
        disk: Disk number

    Returns:
        DiscInfo with episode list, or None if lookup failed
    """
    log.info(f"Looking up {show} Season {season} Disk {disk}...")

    cache_key = _cache_key(show, season, disk)

    # Try cache first
    cached = _load_from_cache(cache_key)
    if cached:
        log.info(f"Using cached disc info: episodes {cached.episodes}")
        return cached

    # Try dvdcompare-scraper
    try:
        from dvdcompare.scraper import search
        results = search(show, season=season)
        if results:
            release = results[0]
            disc_data = release.discs.get(disk)
            if disc_data:
                episodes = []
                for item in disc_data.items:
                    if hasattr(item, 'episode') and item.episode is not None:
                        episodes.append(item.episode)
                if episodes:
                    info = DiscInfo(
                        show=show,
                        season=season,
                        disk=disk,
                        episodes=sorted(episodes),
                        source="dvdcompare"
                    )
                    _save_to_cache(cache_key, info)
                    log.info(f"Found episodes on Disk {disk}: {', '.join(map(str, info.episodes))}")
                    return info
    except (ImportError, Exception):
        pass

    # Try local disc_data.json
    db = _load_disc_database()
    show_key = show.lower().replace(' ', '-')

    # Try lowercase hyphenated key first
    if show_key in db and str(season) in db[show_key]:
        if str(disk) in db[show_key][str(season)]:
            disk_data = db[show_key][str(season)][str(disk)]
            episodes = disk_data.get("episodes") if isinstance(disk_data, dict) else disk_data
            info = DiscInfo(
                show=show,
                season=season,
                disk=disk,
                episodes=sorted(episodes),
                source="local_db"
            )
            _save_to_cache(cache_key, info)
            log.info(f"Found episodes on Disk {disk}: {', '.join(map(str, info.episodes))}")
            return info

    # Fallback: check if key exists with original case
    if show in db and str(season) in db[show]:
        if str(disk) in db[show][str(season)]:
            disk_data = db[show][str(season)][str(disk)]
            episodes = disk_data.get("episodes") if isinstance(disk_data, dict) else disk_data
            info = DiscInfo(
                show=show,
                season=season,
                disk=disk,
                episodes=sorted(episodes),
                source="local_db"
            )
            _save_to_cache(cache_key, info)
            log.info(f"Found episodes on Disk {disk}: {', '.join(map(str, info.episodes))}")
            return info

    log.error(f"Could not find episode info for {show} S{season:02d}D{disk:02d}")
    log.error(f"Add manual mapping to disc_data.json or install dvdcompare-scraper")
    return None


def get_local_db_episodes(
    show: str,
    season: int,
) -> Optional[List[EpisodeMeta]]:
    """
    Get episode metadata from local disc_data.json database.

    This is the primary source - has accurate disk-specific data including real durations.

    Args:
        show: Show name
        season: Season number

    Returns:
        List of EpisodeMeta objects, or None if not found in database
    """
    log.info(f"Looking up {show} Season {season} in local database...")

    db = _load_disc_database()
    show_key = show.lower().replace(' ', '-')

    # Try lowercase hyphenated key first
    if show_key in db and str(season) in db[show_key]:
        disk_data = db[show_key][str(season)]
    # Try original case
    elif show in db and str(season) in db[show]:
        disk_data = db[show][str(season)]
    else:
        log.debug(f"Show '{show}' Season {season} not found in local database")
        return None

    episodes = []
    metadata = {}

    # Aggregate metadata from all disks
    for disk_key, disk in disk_data.items():
        if isinstance(disk, dict):
            if "metadata" in disk:
                metadata.update(disk.get("metadata", {}))

    # Get all episode numbers across all disks
    all_episode_nums = set()
    for disk_key, disk in disk_data.items():
        ep_list = disk.get("episodes") if isinstance(disk, dict) else disk
        all_episode_nums.update(ep_list)

    # Create EpisodeMeta objects
    for ep_num in sorted(all_episode_nums):
        ep_meta = metadata.get(str(ep_num), {})
        episodes.append(EpisodeMeta(
            season=season,
            episode=ep_num,
            title=ep_meta.get("title", f"Episode {ep_num}"),
            runtime_seconds=ep_meta.get("runtime_seconds", 0),
            air_date=ep_meta.get("air_date"),
        ))

    if episodes:
        log.info(f"Retrieved {len(episodes)} episodes from local database")
        return episodes

    return None


def get_dvdcompare_episodes(
    show: str,
    season: int,
) -> Optional[List[EpisodeMeta]]:
    """
    Fetch episode metadata from dvdcompare-scraper (primary source for accurate disk data).

    dvdcompare has actual episode runtimes from physical discs, unlike TMDb which may be inaccurate.

    Args:
        show: Show name
        season: Season number

    Returns:
        List of EpisodeMeta objects, or None if lookup failed
    """
    log.info(f"Fetching {show} Season {season} from dvdcompare...")

    try:
        from dvdcompare.scraper import search
        results = search(show, season=season)

        if not results:
            log.warning(f"Show '{show}' not found on dvdcompare")
            return None

        release = results[0]
        episodes = []

        # Extract episodes from all discs
        for disc_num, disc_data in release.discs.items():
            if disc_data.items:
                for item in disc_data.items:
                    if hasattr(item, 'episode') and item.episode is not None:
                        # Convert duration from seconds to int if available
                        runtime_seconds = 0
                        if hasattr(item, 'duration') and item.duration:
                            # duration might be in seconds or MM:SS format
                            if isinstance(item.duration, int):
                                runtime_seconds = item.duration
                            elif isinstance(item.duration, str):
                                # Parse "MM:SS" or "HH:MM:SS" format
                                parts = item.duration.split(':')
                                if len(parts) == 2:
                                    runtime_seconds = int(parts[0]) * 60 + int(parts[1])
                                elif len(parts) == 3:
                                    runtime_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

                        episode = EpisodeMeta(
                            season=season,
                            episode=item.episode,
                            title=getattr(item, 'title', 'Unknown'),
                            runtime_seconds=runtime_seconds,
                            air_date=None,
                        )
                        episodes.append(episode)

        if episodes:
            # Deduplicate by episode number (in case episode appears on multiple discs)
            seen = {}
            for ep in episodes:
                if ep.episode not in seen:
                    seen[ep.episode] = ep
            episodes = list(seen.values())

            log.info(f"Retrieved {len(episodes)} episodes from dvdcompare")
            return sorted(episodes, key=lambda e: e.episode)

        log.warning(f"No episodes found for {show} Season {season} in dvdcompare")
        return None

    except ImportError:
        log.debug("dvdcompare-scraper not installed, will try TMDb")
        return None
    except Exception as e:
        log.warning(f"Error fetching from dvdcompare: {e}")
        import traceback
        log.debug(traceback.format_exc())
        return None


def get_show_premiere_year(
    show: str,
    api_key: Optional[str] = None,
) -> Optional[int]:
    """
    Get the show's premiere year from TMDb.

    Args:
        show: Show name
        api_key: TMDb API key (uses TMDB_API_KEY env var if not provided)

    Returns:
        Year show premiered (e.g., 2009), or None if lookup failed
    """
    api_key = api_key or TMDB_API_KEY
    if not api_key:
        log.error("TMDB_API_KEY not set. Set environment variable or pass as parameter.")
        return None

    try:
        # Search for show
        search_url = "https://api.themoviedb.org/3/search/tv"
        search_params = {
            "api_key": api_key,
            "query": show,
        }
        search_response = requests.get(search_url, params=search_params, timeout=10)
        search_response.raise_for_status()

        results = search_response.json().get("results", [])
        if not results:
            log.warning(f"Show '{show}' not found on TMDb.")
            return None

        # Get first result's premiere date
        first_result = results[0]
        premiere_date = first_result.get("first_air_date")

        if premiere_date:
            year = int(premiere_date.split("-")[0])
            log.info(f"Show premiere year: {year}")
            return year
        else:
            log.warning(f"No premiere date found for {show}")
            return None

    except requests.RequestException as e:
        log.error(f"TMDb API error: {e}")
        return None
    except (KeyError, ValueError, IndexError) as e:
        log.error(f"Error parsing TMDb response: {e}")
        return None


def get_tmdb_episodes(
    show: str,
    season: int,
    api_key: Optional[str] = None,
) -> Optional[List[EpisodeMeta]]:
    """
    Fetch episode metadata from TMDb API (fallback source).

    Only used if dvdcompare is unavailable. Note: TMDb runtimes may be inaccurate
    for some shows. Prefer dvdcompare data when available.

    Args:
        show: Show name (will search for exact match)
        season: Season number
        api_key: TMDb API key (uses TMDB_API_KEY env var if not provided)

    Returns:
        List of EpisodeMeta objects, or None if lookup failed
    """
    api_key = api_key or TMDB_API_KEY
    if not api_key:
        log.error("TMDB_API_KEY not set. Set environment variable or pass as parameter.")
        return None

    log.info(f"Fetching {show} Season {season} from TMDb (fallback)...")

    try:
        # Search for show
        search_url = "https://api.themoviedb.org/3/search/tv"
        search_params = {
            "api_key": api_key,
            "query": show,
        }
        search_response = requests.get(search_url, params=search_params, timeout=10)
        search_response.raise_for_status()

        results = search_response.json().get("results", [])
        if not results:
            log.warning(f"Show '{show}' not found on TMDb. Check spelling or try alternate name.")
            return None

        show_id = results[0]["id"]
        log.debug(f"Found TMDb show ID: {show_id}")

        # Fetch season episodes
        season_url = f"https://api.themoviedb.org/3/tv/{show_id}/season/{season}"
        season_params = {"api_key": api_key}
        season_response = requests.get(season_url, params=season_params, timeout=10)
        season_response.raise_for_status()

        season_data = season_response.json()
        episodes = []

        for ep_data in season_data.get("episodes", []):
            episodes.append(EpisodeMeta(
                season=season,
                episode=ep_data["episode_number"],
                title=ep_data.get("name", "Unknown"),
                runtime_seconds=int(ep_data.get("runtime", 0) * 60) or 0,
                air_date=ep_data.get("air_date"),
            ))

        log.info(f"Retrieved {len(episodes)} episodes from TMDb")
        return episodes

    except requests.RequestException as e:
        log.error(f"TMDb API error: {e}")
        return None
    except (KeyError, ValueError) as e:
        log.error(f"Error parsing TMDb response: {e}")
        return None


def get_disc_constrained_episodes(
    show: str,
    season: int,
    disk: int,
    api_key: Optional[str] = None,
) -> Tuple[Optional[DiscInfo], Optional[List[EpisodeMeta]]]:
    """
    Get disc info and only the episodes on that disc.

    This is the main entry point for the matching workflow.

    Tries episode metadata sources in order:
    1. dvdcompare-scraper (has accurate disk durations)
    2. TMDb API (fallback, but may have inaccurate runtimes)

    Args:
        show: Show name
        season: Season number
        disk: Disk number
        api_key: TMDb API key (optional, only used as fallback)

    Returns:
        Tuple of (DiscInfo, EpisodeList) or (None, None) if lookup failed
    """
    # Get disc episode list
    disc_info = get_disc_episodes_from_dvdcompare(show, season, disk)
    if not disc_info:
        log.error(f"Could not determine episodes on {show} S{season:02d}D{disk:02d}")
        return None, None

    # Try local database first (primary source - has accurate disk durations)
    all_episodes = get_local_db_episodes(show, season)

    # Fall back to dvdcompare if local DB unavailable
    if not all_episodes:
        log.info("Local database unavailable, trying dvdcompare")
        all_episodes = get_dvdcompare_episodes(show, season)

    # Fall back to TMDb if neither available
    if not all_episodes:
        log.info("dvdcompare unavailable, falling back to TMDb")
        all_episodes = get_tmdb_episodes(show, season, api_key)

    if not all_episodes:
        log.error(f"Could not fetch episodes from dvdcompare or TMDb for {show} Season {season}")
        return None, None

    # Filter to only episodes on this disc
    disc_episodes = [
        ep for ep in all_episodes
        if ep.episode in disc_info.episodes
    ]

    if not disc_episodes:
        log.error(f"No matching episodes found for {show} S{season:02d}D{disk:02d}")
        return None, None

    log.info(f"Matched {len(disc_episodes)} episodes for Disk {disk}")
    return disc_info, disc_episodes
