#!/usr/bin/env python3
"""
Test the full workflow with mock data.

This allows testing the matching, reporting, and output generation
without needing ffprobe to extract real MKV durations.
"""

import json
import sys
import io

# Handle Unicode output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from matcher import RippedFile, EpisodeTarget, match_files
from reporting import generate_text_report, generate_mapping_json


def test_community_season1_disk2():
    """Test with Community Season 1 Disk 2 (episodes 14-25)."""

    # Mock episode data from TMDb (approximate runtimes in seconds)
    episodes = [
        EpisodeTarget("Community", 1, 14, "Interpretive Dance", 2460),
        EpisodeTarget("Community", 1, 15, "Conspiracy Weirdness", 2535),
        EpisodeTarget("Community", 1, 16, "Romantic Expressionism", 2465),
        EpisodeTarget("Community", 1, 17, "Physical Education", 2520),
        EpisodeTarget("Community", 1, 18, "Advanced Criminal Law", 2545),
        EpisodeTarget("Community", 1, 19, "Debate 109", 2470),
        EpisodeTarget("Community", 1, 20, "The Art of Discourse", 2550),
        EpisodeTarget("Community", 1, 21, "Contemporary Impressionists", 2551),
        EpisodeTarget("Community", 1, 22, "The Art of Discourse (cont)", 2515),
        EpisodeTarget("Community", 1, 23, "Modern Espionage", 2480),
        EpisodeTarget("Community", 1, 24, "English as a Second Language", 2510),
        EpisodeTarget("Community", 1, 25, "Introduction to Political Science", 2590),
    ]

    # Mock ripped files (with realistic duration variations)
    files = [
        RippedFile("title_t00.mkv", 2460),   # E14
        RippedFile("title_t01.mkv", 2536),   # E15 (off by 1s)
        RippedFile("title_t02.mkv", 2465),   # E16
        RippedFile("title_t03.mkv", 2520),   # E17
        RippedFile("title_t04.mkv", 2545),   # E18
        RippedFile("title_t05.mkv", 2470),   # E19
        RippedFile("title_t06.mkv", 2550),   # E20
        RippedFile("title_t07.mkv", 2600),   # E21 (different, needs review)
        RippedFile("title_t08.mkv", 2514),   # E22 (off by 1s)
        RippedFile("title_t09.mkv", 2480),   # E23
        RippedFile("title_t10.mkv", 2510),   # E24
        RippedFile("title_t11.mkv", 2590),   # E25
    ]

    # Disk constraint: episodes 14-25
    disk_episodes = [14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]

    # Run matching
    results = match_files(files, episodes, disk_episodes)

    # Generate report
    report = generate_text_report(results, "Community", 1, 2)
    print(report)

    # Generate mapping
    mapping = generate_mapping_json(results, "Community")
    print("\n\nGenerated Mapping:")
    print(json.dumps(mapping, indent=2))


if __name__ == "__main__":
    test_community_season1_disk2()
