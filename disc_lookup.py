"""
Disc metadata lookup from dvdcompare.net and TMDb.
"""

import logging
from typing import Optional, List, Dict
from dataclasses import dataclass
import requests
from pathlib import Path
import json

from config import TMDB_API_KEY, DVDCOMPARE_CACHE_TTL

log = logging.getLogger(__name__)


@dataclass
class DiscInfo:
    """Information about a physical disc."""
    show: str
    season: int
    disk: int
    episodes: List[int]  # Episode numbers on this disk
    release_region: Optional[str] = None


@dataclass
class EpisodeMeta:
    """Episode metadata from TMDb."""
    season: int
    episode: int
    title: str
    runtime_seconds: int
    air_date: Optional[str] = None


def get_disc_episodes_from_dvdcompare(
    show: str,
    season: int,
    disk: int,
) -> Optional[DiscInfo]:
    """
    Look up which episodes are on this disk from dvdcompare.net

    This will be implemented with dvdcompare-scraper library.
    For now, returns None (fallback needed).
    """
    log.info(f"Looking up {show} Season {season} Disk {disk} on dvdcompare.net...")

    # TODO: Implement dvdcompare-scraper integration
    # dvdcompare_scraper.search(show, season, disk)

    log.warning("dvdcompare lookup not yet implemented")
    return None


def get_tmdb_episodes(
    show: str,
    season: int,
    api_key: Optional[str] = None,
) -> Optional[List[EpisodeMeta]]:
    """
    Fetch episode metadata from TMDb API.

    Args:
        show: Show name (must match TMDb exactly)
        season: Season number
        api_key: TMDb API key (uses TMDB_API_KEY env var if not provided)

    Returns:
        List of EpisodeMeta objects, or None if lookup failed
    """
    api_key = api_key or TMDB_API_KEY
    if not api_key:
        log.error("TMDB_API_KEY not set")
        return None

    log.info(f"Looking up {show} Season {season} on TMDb...")

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
            log.warning(f"Show '{show}' not found on TMDb")
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
