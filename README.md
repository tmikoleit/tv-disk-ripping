# Disk Ripping Automation Tool

Automatic episode matching and file organization for MakeMKV rips. Uses dvdcompare.net and TMDb to match ripped MKV files to episodes, with disc-aware constraints and ambiguity detection.

## Features

- ✅ **Disc-aware matching** — Only considers episodes on the current disk
- ✅ **Confidence scoring** — HIGH (≤30s), MEDIUM (≤120s), LOW (>120s)
- ✅ **Ambiguity detection** — Flags potential mismatches for review
- ✅ **Bulk processing** — Process single disks, entire seasons, or full shows
- ✅ **Interactive workflow** — Run via Claude Code, review results, request revisions
- ✅ **Mapping persistence** — Save JSON mappings for Plex naming

## Quick Start

### Setup

```bash
# Install Python 3.9+
# Set environment variables
set TMDB_API_KEY=your_api_key_here

# Install dependencies
pip install -r requirements.txt
```

### Usage

```bash
# Single disk
python process_rips.py community 1 2

# All disks in a season
python process_rips.py community --season 1

# All disks in all seasons
python process_rips.py community --all

# Preview mode (no changes)
python process_rips.py community 1 2 --preview
```

## Workflow

1. **Rip with MakeMKV** → `D:\Disk Ripping\[Show]\Season [N]\Disk [N]\`
2. **Run tool** → `python process_rips.py [show] [season] [disk]`
3. **Review report** → Check for matches, ambiguities, confidence scores
4. **Request changes** → Tell Claude what needs fixing
5. **Rename files** → Use generated mapping JSON with your renaming tool

## Directory Structure

```
D:\Disk Ripping\
├── [Show Name]/
│   ├── Season 1/
│   │   ├── Disk 1/
│   │   │   ├── title_t00.mkv
│   │   │   └── ...
│   │   └── Disk 2/
│   ├── mappings/
│   │   ├── S01D01.json
│   │   └── ...
│   └── reports/
│       ├── S01D01_report.txt
│       └── ...
└── Completed/  (for organized output)
```

## Report Format

Each run generates a single combined report showing:

- **Matched Files** — All episodes matched with confidence levels
- **Ambiguous Matches** — Episodes with multiple possible matches
- **Unmatched Files** — MKV files that couldn't be matched
- **Summary** — Total matches, confidence distribution, action items

## Interactive Workflow

This tool is designed to be run via Claude Code with interactive refinement:

```
You: "Process Community Season 1 Disk 2"
Claude: Runs tool, shows report
You: "title_t03.mkv is wrong, should be S01E20"
Claude: Revises mapping, reruns validation
You: "Perfect, apply it"
Claude: Commits to git, ready for next disk
```

## Disk Constraint Guarantee

Every run validates that:
- Only episodes from the specified disk are considered
- No cross-disk episode leakage
- Bulk runs maintain per-disk integrity

## Version History

All changes are committed to git for full traceability:
```bash
git log --oneline
```

## Development

See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for architecture, testing, and contribution guidelines.

---

**Status:** Beta (under active development)  
**Last Updated:** 2026-06-18  
**Next Phase:** Core implementation and Community Season 1 testing
