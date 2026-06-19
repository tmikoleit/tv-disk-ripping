#!/usr/bin/env python3
"""
Main CLI entry point for disk ripping automation.

Usage:
  python process_rips.py community 1 2          # Single disk
  python process_rips.py community --season 1   # All disks in season
  python process_rips.py community --all        # All disks in show
"""

import click
import logging
import sys
from pathlib import Path
from typing import List, Tuple

import disc_lookup
import file_scanner
import matcher
import reporting
from config import BASE_DIR, TMDB_API_KEY

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
log = logging.getLogger(__name__)


def find_disks(show_path: Path, season: int = None) -> List[Tuple[int, int]]:
    """
    Find all Season/Disk folders in show directory.

    Returns:
        List of (season, disk) tuples sorted by season then disk
    """
    disks = []

    for season_dir in sorted(show_path.glob("Season *")):
        try:
            season_num = int(season_dir.name.split()[-1])
            if season is not None and season_num != season:
                continue

            for disk_dir in sorted(season_dir.glob("Disk *")):
                try:
                    disk_num = int(disk_dir.name.split()[-1])
                    disks.append((season_num, disk_num))
                except ValueError:
                    pass

        except ValueError:
            pass

    return disks


def process_single_disk(
    show: str,
    season: int,
    disk: int,
    preview: bool = False,
) -> None:
    """
    Process a single disk: lookup, match, generate report and mapping.

    Args:
        show: Show name
        season: Season number
        disk: Disk number
        preview: If True, don't write files
    """
    show_path = BASE_DIR / show
    disk_path = show_path / f"Season {season}" / f"Disk {disk}"

    if not disk_path.exists():
        click.echo(f"❌ Directory not found: {disk_path}")
        sys.exit(1)

    click.echo(f"\n{'=' * 80}")
    click.echo(f"Processing: {show} S{season:02d}D{disk:02d}")
    click.echo(f"Location: {disk_path}")
    click.echo(f"{'=' * 80}\n")

    # Step 1: Get disc episodes and TMDb metadata
    click.echo(f"📡 Looking up disc content...")
    disc_info, episodes = disc_lookup.get_disc_constrained_episodes(
        show, season, disk, TMDB_API_KEY
    )

    if not disc_info or not episodes:
        click.echo(f"❌ Could not retrieve disc/episode information")
        click.echo(f"\nTroubleshooting:")
        click.echo(f"  1. Verify show name matches TMDb exactly")
        click.echo(f"  2. Try searching on https://www.themoviedb.org/")
        click.echo(f"  3. Check TMDB_API_KEY environment variable is set")
        sys.exit(1)

    click.echo(f"✓ Found {len(disc_info.episodes)} episodes on disk: {disc_info.episodes}")
    click.echo(f"✓ Retrieved metadata from TMDb\n")

    # Step 2: Scan ripped files
    click.echo(f"📁 Scanning MKV files...")
    ripped_files = file_scanner.scan_disk_folder(disk_path)

    if not ripped_files:
        click.echo(f"❌ No MKV files found in {disk_path}")
        sys.exit(1)

    click.echo(f"✓ Found {len(ripped_files)} MKV files\n")

    # Step 3: Match files to episodes
    click.echo(f"🔍 Matching files to episodes...")
    file_objs = [
        matcher.RippedFile(name, duration)
        for name, duration in ripped_files
    ]

    episode_targets = [
        matcher.EpisodeTarget(
            show=show,
            season=ep.season,
            episode=ep.episode,
            title=ep.title,
            runtime_seconds=ep.runtime_seconds,
        )
        for ep in episodes
    ]

    results = matcher.match_files(
        file_objs,
        episode_targets,
        disk_episodes=disc_info.episodes
    )

    click.echo(f"✓ Matching complete\n")

    # Step 4: Generate report
    click.echo(f"📊 Generating report...")
    report_text = reporting.generate_text_report(results, show, season, disk)
    click.echo(report_text)

    # Step 5: Save files
    if preview:
        click.echo(f"\n[PREVIEW MODE - No files written]\n")
    else:
        click.echo(f"\n💾 Saving files...")

        report_path = reporting.save_report(report_text, show, season, disk, BASE_DIR / show)
        click.echo(f"   Report: {report_path.relative_to(BASE_DIR)}")

        mapping = reporting.generate_mapping_json(results, show)
        mapping_path = reporting.save_mapping_json(mapping, show, season, disk, BASE_DIR / show)
        click.echo(f"   Mapping: {mapping_path.relative_to(BASE_DIR)}")

    click.echo(f"\n{'=' * 80}")
    click.echo(f"Ready for next step")
    click.echo(f"{'=' * 80}\n")


@click.command()
@click.argument('show', type=str)
@click.argument('season', type=int, required=False, default=None)
@click.argument('disk', type=int, required=False, default=None)
@click.option('--season', 'season_opt', type=int, help='Process all disks in this season')
@click.option('--all', 'process_all', is_flag=True, help='Process all disks in show')
@click.option('--preview', is_flag=True, help='Preview changes without writing')
def main(show, season, disk, season_opt, process_all, preview):
    """
    Process disk rips and generate episode mappings.

    SHOW: Show name (e.g., "Community")
    SEASON: Season number (required unless using --season or --all)
    DISK: Disk number (required unless using --season or --all)
    """

    # Validate arguments
    if season_opt and season:
        click.echo("❌ Error: Cannot use both positional SEASON and --season flag")
        sys.exit(1)

    if not (process_all or season_opt or (season is not None and disk is not None)):
        click.echo("❌ Error: Must provide SEASON and DISK, or use --season, or use --all")
        sys.exit(1)

    # Resolve mode
    if process_all:
        target_season = None
    elif season_opt:
        target_season = season_opt
    else:
        target_season = season

    try:
        show_path = BASE_DIR / show
        if not show_path.exists():
            click.echo(f"❌ Show directory not found: {show_path}")
            sys.exit(1)

        # Find disks to process
        disks_to_process = find_disks(show_path, target_season)

        if not disks_to_process:
            click.echo(f"❌ No disks found")
            sys.exit(1)

        # Single disk
        if season is not None and disk is not None:
            if (season, disk) not in disks_to_process:
                click.echo(f"❌ Disk not found: {show} S{season:02d}D{disk:02d}")
                sys.exit(1)
            process_single_disk(show, season, disk, preview)

        # Multiple disks
        else:
            click.echo(f"\n{'=' * 80}")
            click.echo(f"Processing: {show}")
            if target_season:
                click.echo(f"Season: {target_season}")
            else:
                click.echo(f"All seasons and disks")
            click.echo(f"Found {len(disks_to_process)} disk(s) to process")
            click.echo(f"{'=' * 80}\n")

            for s, d in disks_to_process:
                try:
                    process_single_disk(show, s, d, preview)
                except SystemExit:
                    click.echo(f"⚠️  Skipping S{s:02d}D{d:02d} due to error\n")
                    continue

            click.echo(f"\n{'=' * 80}")
            click.echo(f"✓ Batch processing complete")
            click.echo(f"{'=' * 80}\n")

    except Exception as e:
        log.error(f"❌ Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
