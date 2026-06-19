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


def get_disc_episodes_from_dvdcompare(
    show: str,
    season: int,
    disk: int,
) -> Optional[DiscInfo]:
    """
    Look up which episodes are on this disk from dvdcompare.net

    Uses dvdcompare-scraper library to query disc metadata.
    Caches results locally for 24 hours.

    Args:
        show: Show name
        season: Season number
        disk: Disk number

    Returns:
        DiscInfo with episode list, or None if lookup failed
    """
    log.info(f"Looking up {show} Season {season} Disk {disk} on dvdcompare.net...")

    cache_key = _cache_key(show, season, disk)

    # Try cache first
    cached = _load_from_cache(cache_key)
    if cached:
        log.info(f"Using cached disc info: {', '.join(map(str, cached.episodes))}")
        return cached

    try:
        # Import here to avoid hard dependency if library isn't installed
        from dvdcompare_scraper import search

        # Search for disc set
        results = search(show, season=season)

        if not results:
            log.warning(f"No results for {show} Season {season}")
            return None

        # Get first result (most likely match)
        release = results[0]
        log.debug(f"Found release: {release}")

        # Get episodes for this disk
        disc_data = release.discs.get(disk)
        if not disc_data:
            log.warning(f"Disk {disk} not found in release")
            return None

        # Extract episode numbers from disc
        episodes = []
        for item in disc_data.items:
            if hasattr(item, 'episode') and item.episode is not None:
                episodes.append(item.episode)

        if not episodes:
            log.warning(f"No episodes found on Disk {disk}")
            return None

        info = DiscInfo(
            show=show,
            season=season,
            disk=disk,
            episodes=sorted(episodes),
            release_region=release.region if hasattr(release, 'region') else None,
            source="dvdcompare"
        )

        _save_to_cache(cache_key, info)
        log.info(f"Found episodes on Disk {disk}: {', '.join(map(str, info.episodes))}")
        return info

    except ImportError:
        log.error("dvdcompare-scraper not installed. Install: pip install dvdcompare-scraper")
        return None
    except Exception as e:
        log.error(f"dvdcompare lookup failed: {e}")
        return None


def get_tmdb_episodes(
    show: str,
    season: int,
    api_key: Optional[str] = None,
) -> Optional[List[EpisodeMeta]]:
    """
    Fetch episode metadata from TMDb API.

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

    log.info(f"Fetching {show} Season {season} from TMDb...")

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

    Args:
        show: Show name
        season: Season number
        disk: Disk number
        api_key: TMDb API key (optional)

    Returns:
        Tuple of (DiscInfo, EpisodeList) or (None, None) if lookup failed
    """
    # Get disc episode list
    disc_info = get_disc_episodes_from_dvdcompare(show, season, disk)
    if not disc_info:
        log.error(f"Could not determine episodes on {show} S{season:02d}D{disk:02d}")
        return None, None

    # Get all episodes from TMDb
    all_episodes = get_tmdb_episodes(show, season, api_key)
    if not all_episodes:
        log.error(f"Could not fetch episodes from TMDb for {show} Season {season}")
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
