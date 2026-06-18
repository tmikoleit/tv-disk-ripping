# Disk Ripping Automation

Fully automated Blu-ray/DVD ripping and file organization for Plex using MakeMKV, TMDb metadata, and PowerShell.

## Overview

- **Generate-MappingFromMetadata.ps1** — Fetches episode data from TMDb, matches ripped files by duration, auto-renames to FileBot format
- **Rename-DiskRips.ps1** — Applies mappings, renames files, and moves to organized Completed folder

## Features

✅ **Fully Automated** — No manual episode matching  
✅ **Millisecond Precision** — Disambiguates files with identical duration  
✅ **Ambiguous Match Alerts** — Flags episodes needing manual verification  
✅ **Generic** — Works with any show on TMDb  
✅ **Year-Aware Folders** — `Show Name (YYYY)/Season N/`  
✅ **Accumulates Disks** — Multiple disks append to same season folder  
✅ **Plex-Ready** — FileBot naming format  

## Quick Start

### Prerequisites
- TMDb API key: https://www.themoviedb.org/settings/api
- ffprobe (optional): `choco install ffmpeg -y`
- PowerShell 5.1+

### Usage

```powershell
# Set API key
$env:TMDB_API_KEY = "your_api_key"

# Generate mapping + rename
D:\Disk Ripping\Generate-MappingFromMetadata.ps1 -Show "Show Name" -Season 1 -Disk 1 -AutoRename

# Move to Completed folder
D:\Disk Ripping\Rename-DiskRips.ps1 -Show "Show Name" -Season 1 -Disk 1 -MoveToCompleted

# Move to Plex
Move-Item "D:\Disk Ripping\Completed\Show Name (YYYY)\Season 1\*.mkv" "D:\Plex Library\Show Name\Season 1\"
```

## Directory Structure

**Working:**
```
D:\Disk Ripping\
├── [Show]/
│   ├── mappings/
│   │   └── S[N]D[N].json (generated)
│   └── Season [N]/
│       └── Disk [N]/ (ripped files)
```

**Completed:**
```
D:\Disk Ripping\Completed\
└── [Show] (YYYY)/
    └── Season [N]/ (all disks accumulated)
```

## Output Format

Files are renamed to FileBot standard:
```
Breaking Bad - S01E01 - Pilot.mkv
Breaking Bad - S01E02 - Cat's in the Bag....mkv
```

## Troubleshooting

**"API key required"**
```powershell
$env:TMDB_API_KEY = "your_key"
```

**"Could not find '[Show]' on TMDb"**
- Try alternate name (e.g., "The Office (US)")
- Verify on https://www.themoviedb.org

**Duration mismatch**
- Install ffprobe for better precision
- Tolerance is ±90 seconds for Blu-ray variations

**Ambiguous matches**
- Script flags episodes with identical durations
- Check millisecond precision and verify manually if needed

## Performance

- Ripping: 30-90 min/disk (depends on tracks)
- Processing: 10-30 sec/disk (metadata + matching)

## Version History

See git history for changes. Latest: Enhanced millisecond precision matching with per-season/disk scoping.

---

**Status:** Production-Ready | **Tested:** Community, The Northman
