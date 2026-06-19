#!/usr/bin/env python3
"""Analyze episode runtimes to identify truly ambiguous files."""

import sys
import io
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

try:
    import disc_lookup
    from config import TMDB_API_KEY

    disc_info, episodes = disc_lookup.get_disc_constrained_episodes(
        "Community", 1, 2, TMDB_API_KEY
    )

    print("\n" + "="*80)
    print("COMMUNITY S01D02 - EPISODE RUNTIMES")
    print("="*80)

    # Show all episodes with their runtimes
    for ep in sorted(episodes, key=lambda x: x.episode):
        print(f"E{ep.episode:02d} | {ep.runtime_seconds:4d}s ({ep.runtime_seconds//60}m) | {ep.title}")

    # Group by runtime
    from collections import defaultdict
    runtime_groups = defaultdict(list)
    for ep in episodes:
        runtime_groups[ep.runtime_seconds].append(ep)

    print("\n" + "="*80)
    print("EPISODES WITH IDENTICAL RUNTIMES (AMBIGUOUS CLUSTERS)")
    print("="*80 + "\n")

    has_duplicates = False
    for runtime in sorted(runtime_groups.keys()):
        eps = runtime_groups[runtime]
        if len(eps) > 1:
            has_duplicates = True
            ep_nums = [e.episode for e in sorted(eps, key=lambda x: x.episode)]
            print(f"🔀 Runtime {runtime}s ({runtime//60}m):")
            for ep in sorted(eps, key=lambda x: x.episode):
                print(f"   E{ep.episode:02d}: {ep.title}")
            print()

    if not has_duplicates:
        print("✓ No duplicate runtimes - all episodes are unique!")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
