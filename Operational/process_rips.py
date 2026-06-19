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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


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
    if not (process_all or season_opt or (season and disk)):
        click.echo("Error: Must provide SEASON and DISK, or use --season, or use --all")
        sys.exit(1)

    if season_opt and season:
        click.echo("Error: Cannot use both positional SEASON and --season flag")
        sys.exit(1)

    try:
        # TODO: Implement core logic
        click.echo(f"Show: {show}")
        if process_all:
            click.echo("Mode: Process all seasons and disks")
        elif season_opt:
            click.echo(f"Mode: Process all disks in season {season_opt}")
        else:
            click.echo(f"Mode: Single disk S{season:02d}D{disk:02d}")

        if preview:
            click.echo("[PREVIEW MODE - No changes will be made]")

        click.echo("\n🔧 Implementation in progress...")

    except Exception as e:
        log.error(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
