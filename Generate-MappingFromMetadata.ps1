param(
    [Parameter(Mandatory=$true)]
    [string]$Show,           # Show name (e.g., "Community")

    [Parameter(Mandatory=$true)]
    [int]$Season,            # Season number (1-based)

    [int]$Disk = 1,          # Disk number (optional, defaults to 1)

    [string]$TMDbApiKey,     # TMDb API key (or set as env var TMDB_API_KEY)

    [string]$DiscDbUrl,      # TheDiscDB URL (optional, auto-discovered if not provided)

    [string]$ManualEpisodes, # Manual episode range (e.g., "14-25") if disk info unavailable

    [switch]$AutoRename      # Auto-rename files after mapping
)

$baseDir = "D:\Disk Ripping"

# Get TMDb API key
if (-not $TMDbApiKey) {
    $TMDbApiKey = $env:TMDB_API_KEY
}

if (-not $TMDbApiKey) {
    Write-Host "Error: TMDb API key required" -ForegroundColor Red
    Write-Host "Set TMDB_API_KEY environment variable or pass -TMDbApiKey" -ForegroundColor Yellow
    exit 1
}

function Get-FileDuration {
    param([string]$FilePath, [bool]$IncludeMs = $false)

    # Try ffprobe first (most accurate, supports milliseconds)
    $ffprobe = (Get-Command ffprobe -ErrorAction SilentlyContinue).Source

    if ($ffprobe) {
        try {
            $json = & ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1:nokey=1 "$FilePath" 2>$null
            if ($json) {
                $durationSecs = [double]$json
                if ($IncludeMs) {
                    return $durationSecs  # Returns float with millisecond precision
                } else {
                    return [int]$durationSecs  # Returns integer seconds
                }
            }
        } catch {
            # Fall through to shell method
        }
    }

    # Fallback: use Windows Shell.Application (no millisecond precision)
    try {
        $shell = New-Object -ComObject Shell.Application
        $folder = $shell.Namespace((Split-Path $FilePath))
        $file = $folder.ParseName((Split-Path $FilePath -Leaf))

        # Duration is typically in field 27 for media files
        $duration = $file.ExtendedProperty("System.Media.Duration")

        if ($duration) {
            # Duration is in 100-nanosecond intervals
            $durationSecs = [int]($duration / 10000000)
            if ($IncludeMs) {
                $durationMs = $duration / 10000
                return $durationMs / 1000
            } else {
                return $durationSecs
            }
        }
    } catch {
        Write-Host "Warning: Could not determine duration for $FilePath" -ForegroundColor Yellow
    }

    return $null
}

function Get-TMDbShowInfo {
    param([string]$ShowName)

    $url = "https://api.themoviedb.org/3/search/tv?api_key=$TMDbApiKey&query=$([Uri]::EscapeDataString($ShowName))"

    try {
        $response = Invoke-RestMethod -Uri $url -ErrorAction Stop

        if ($response.results -and $response.results.Count -gt 0) {
            $show = $response.results[0]
            $year = $null
            if ($show.first_air_date) {
                $year = [datetime]::ParseExact($show.first_air_date, "yyyy-MM-dd", $null).Year
            }
            return @{ id = $show.id; year = $year }
        }
    } catch {
        Write-Host "Error searching TMDb: $($_.Exception.Message)" -ForegroundColor Red
    }

    return $null
}

function Get-TMDbEpisodes {
    param([int]$ShowId, [int]$Season)

    $url = "https://api.themoviedb.org/3/tv/$ShowId/season/$Season`?api_key=$TMDbApiKey"

    try {
        $response = Invoke-RestMethod -Uri $url -ErrorAction Stop

        if ($response.episodes) {
            return $response.episodes | Sort-Object episode_number
        }
    } catch {
        Write-Host "Error fetching episodes from TMDb: $($_.Exception.Message)" -ForegroundColor Red
    }

    return $null
}

function Get-DiscDbEpisodes {
    param([string]$DiscDbUrl)

    try {
        $response = Invoke-WebRequest -Uri $DiscDbUrl -ErrorAction Stop
        $html = $response.Content

        # Extract episode list from HTML - look for numbered list items with episode names
        $episodeMatches = [regex]::Matches($html, '<li[^>]*>.*?<strong>(\d+)\.\s*"([^"]+)"')

        if ($episodeMatches.Count -eq 0) {
            # Try alternative pattern
            $episodeMatches = [regex]::Matches($html, '"([^"]+)"')
        }

        if ($episodeMatches.Count -gt 0) {
            $episodes = @()
            foreach ($match in $episodeMatches) {
                $episodes += @{
                    position = $episodes.Count + 1
                    title = $match.Groups[2].Value
                }
            }
            return $episodes
        }
    } catch {
        Write-Host "Error fetching DiscDB page: $($_.Exception.Message)" -ForegroundColor Red
    }

    return $null
}

function Invoke-DiscDbLookup {
    param(
        [string]$ShowName,
        [int]$Season,
        [int]$Disk
    )

    Write-Host "Attempting to find TheDiscDB entry for $ShowName Season $Season Disk $Disk..." -ForegroundColor Gray

    # Common patterns for TheDiscDB URLs
    $showSlug = $ShowName.ToLower() -replace '\s+', '-'
    $commonPatterns = @(
        "https://thediscdb.com/series/$showSlug-2009/releases/2018-complete-series-blu-ray/discs/s$('{0:D2}' -f $Season)d$('{0:D2}' -f $Disk)",
        "https://thediscdb.com/series/$showSlug/releases/2018-complete-series-blu-ray/discs/s$('{0:D2}' -f $Season)d$('{0:D2}' -f $Disk)",
        "https://thediscdb.com/series/$showSlug/releases/complete-series-blu-ray/discs/s$('{0:D2}' -f $Season)d$('{0:D2}' -f $Disk)"
    )

    foreach ($pattern in $commonPatterns) {
        Write-Host "  Trying: $pattern" -ForegroundColor DarkGray
        try {
            $response = Invoke-WebRequest -Uri $pattern -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Host "  ✓ Found!" -ForegroundColor Green
                return $pattern
            }
        } catch {
            # Continue to next pattern
        }
    }

    return $null
}

function Get-DiskEpisodesFromDiscDb {
    param(
        [string]$DiscDbUrl,
        [int]$FirstEpisodeNumber,
        [array]$AllSeasonEpisodes
    )

    Write-Host "Fetching episode list from TheDiscDB..." -ForegroundColor Gray

    try {
        $response = Invoke-WebRequest -Uri $DiscDbUrl -ErrorAction Stop
        $html = $response.Content

        # Extract episode titles from the page
        # Pattern: episode list items with quoted titles
        $episodeMatches = [regex]::Matches($html, '"([^"]+)"', 'IgnoreCase')

        if ($episodeMatches.Count -gt 0) {
            $diskEpisodes = @()
            for ($i = 0; $i -lt $episodeMatches.Count; $i++) {
                $title = $episodeMatches[$i].Groups[1].Value
                $epNum = $FirstEpisodeNumber + $i

                # Find matching episode in the full season data
                $matchedEp = $AllSeasonEpisodes | Where-Object { $_.episode_number -eq $epNum }
                if ($matchedEp -and $matchedEp.name -eq $title) {
                    $diskEpisodes += $matchedEp
                }
            }

            if ($diskEpisodes.Count -gt 0) {
                return $diskEpisodes
            }
        }
    } catch {
        Write-Host "Error reading DiscDB content: $($_.Exception.Message)" -ForegroundColor Red
    }

    return $null
}

function Get-DiskEpisodesManually {
    param([array]$AllSeasonEpisodes)

    Write-Host ""
    Write-Host "TheDiscDB lookup unavailable. Please provide episode numbers for this disk." -ForegroundColor Yellow
    Write-Host "Example: 14-25 (for episodes 14 through 25)" -ForegroundColor Gray
    $input = Read-Host "Episode range"

    if ($input -match '^(\d+)-(\d+)$') {
        $start = [int]$matches[1]
        $end = [int]$matches[2]

        $diskEpisodes = $AllSeasonEpisodes | Where-Object { $_.episode_number -ge $start -and $_.episode_number -le $end }

        if ($diskEpisodes.Count -gt 0) {
            return $diskEpisodes
        }
    }

    Write-Host "Invalid range. Please use format: START-END" -ForegroundColor Red
    return $null
}

function Match-FilesToEpisodes {
    param(
        [hashtable]$FileInfos,      # @{ filename = duration_in_seconds }
        [hashtable]$FileInfosMs,    # @{ filename = duration_with_ms }
        [array]$Episodes            # TMDb episodes array (same season only)
    )

    $matches = @{}
    $unmatched = @()
    $ambiguous = @()
    $tolerance = 90  # Allow 90 seconds variation (Blu-ray can differ from TV runtimes)
    $matchedFiles = @()  # Track which files have been matched

    # SCOPING: Episodes parameter contains ONLY episodes from the specific season requested
    # This prevents cross-season or cross-show matching

    foreach ($episode in $Episodes) {
        $episodeRuntime = $episode.runtime * 60  # Convert minutes to seconds
        $bestMatch = $null
        $bestDiff = $tolerance + 1
        $matchesWithinTolerance = @()  # Track all matches within tolerance

        foreach ($fileName in $FileInfos.Keys) {
            # Skip files already matched to another episode
            if ($matchedFiles -contains $fileName) {
                continue
            }

            $fileDuration = $FileInfos[$fileName]
            $diff = [Math]::Abs($fileDuration - $episodeRuntime)

            if ($diff -lt $bestDiff) {
                $bestMatch = $fileName
                $bestDiff = $diff
            }

            # Track all matches within tolerance for ambiguity detection
            if ($diff -le $tolerance) {
                $matchesWithinTolerance += @{ file = $fileName; diff = $diff; duration = $fileDuration; durationMs = $FileInfosMs[$fileName] }
            }
        }

        if ($bestMatch -and $bestDiff -le $tolerance) {
            # Check if there are multiple files with identical (or near-identical) durations
            $identicalDurationFiles = $matchesWithinTolerance | Where-Object { [Math]::Abs($_.diff - $bestDiff) -lt 0.01 }

            if ($identicalDurationFiles.Count -gt 1) {
                $ambiguousEp = "E$('{0:D2}' -f $episode.episode_number): $($episode.name) - MULTIPLE FILES WITH SAME DURATION:"
                foreach ($match in $identicalDurationFiles) {
                    $ambiguousEp += "`n    | $($match.file): $([Math]::Round($match.durationMs, 3))s"
                }
                $ambiguous += $ambiguousEp
            }

            $matches[$episode.episode_number] = $bestMatch
            $matchedFiles += $bestMatch  # Mark this file as matched
        } else {
            $unmatched += "E$('{0:D2}' -f $episode.episode_number): Runtime $episodeRuntime`s (no file within ${tolerance}s tolerance)"
        }
    }

    return @{ matches = $matches; unmatched = $unmatched; ambiguous = $ambiguous }
}

function Build-Mapping {
    param(
        [hashtable]$Matches,        # @{ episode_number = filename }
        [array]$Episodes,           # TMDb episodes
        [int]$Season,
        [string]$ShowName
    )

    $mapping = @{}

    foreach ($episode in $Episodes) {
        $epNum = $episode.episode_number

        if ($Matches.ContainsKey($epNum)) {
            $fileName = $Matches[$epNum]
            $episodeName = $episode.name
            $newName = "$ShowName - S$('{0:D2}' -f $Season)E$('{0:D2}' -f $epNum) - $episodeName.mkv"

            # Clean up invalid filename characters
            $newName = $newName -replace '[<>:"/\\|?*]', '-'

            $mapping[$fileName] = $newName
        }
    }

    return $mapping
}

# Main execution
Write-Host "`n" -NoNewline
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "TMDB-BASED MAPPING GENERATOR" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

$diskPath = Join-Path $baseDir $Show | Join-Path -ChildPath "Season $Season" | Join-Path -ChildPath "Disk $Disk"

if (-not (Test-Path $diskPath)) {
    Write-Host "Error: Disk path not found: $diskPath" -ForegroundColor Red
    exit 1
}

Write-Host "Getting episode data from TMDb..." -ForegroundColor Gray
$showInfo = Get-TMDbShowInfo -ShowName $Show

if (-not $showInfo) {
    Write-Host "Error: Could not find '$Show' on TMDb" -ForegroundColor Red
    exit 1
}

$showId = $showInfo.id
$showYear = $showInfo.year

Write-Host "Found: TMDb ID $showId" -ForegroundColor Green
if ($showYear) {
    Write-Host "Premiere year: $showYear" -ForegroundColor Green
}

$episodes = Get-TMDbEpisodes -ShowId $showId -Season $Season

if (-not $episodes) {
    Write-Host "Error: Could not fetch episodes for Season $Season" -ForegroundColor Red
    exit 1
}

Write-Host "Found $($episodes.Count) episodes on TMDb for Season $Season" -ForegroundColor Green
Write-Host ""

# Try to get disk-specific episodes from TheDiscDB
$diskEpisodes = $null
$diskSource = $null

if ($ManualEpisodes) {
    # User provided manual episode range
    Write-Host "Using manual episode range: $ManualEpisodes" -ForegroundColor Gray
    $diskEpisodes = Get-DiskEpisodesManually -AllSeasonEpisodes $episodes
    $diskSource = "Manual"
} elseif ($DiscDbUrl) {
    # User provided DiscDB URL directly
    Write-Host "Using provided DiscDB URL..." -ForegroundColor Gray
    $diskEpisodes = Get-DiskEpisodesFromDiscDb -DiscDbUrl $DiscDbUrl -FirstEpisodeNumber 1 -AllSeasonEpisodes $episodes
    $diskSource = "DiscDB (provided)"
} else {
    # Try to auto-discover DiscDB URL
    $foundUrl = Invoke-DiscDbLookup -ShowName $Show -Season $Season -Disk $Disk
    if ($foundUrl) {
        $diskEpisodes = Get-DiskEpisodesFromDiscDb -DiscDbUrl $foundUrl -FirstEpisodeNumber 1 -AllSeasonEpisodes $episodes
        $diskSource = "DiscDB (auto-found)"
    } else {
        # Ask user for URL or manual entry
        Write-Host ""
        Write-Host "Could not auto-discover TheDiscDB entry." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Options:" -ForegroundColor Cyan
        Write-Host "1. Provide TheDiscDB URL manually" -ForegroundColor Gray
        Write-Host "2. Enter episode numbers manually (e.g., 14-25)" -ForegroundColor Gray
        Write-Host "3. Skip disk info and match across entire season" -ForegroundColor Gray
        Write-Host ""

        $choice = Read-Host "Enter choice (1-3)"

        switch ($choice) {
            "1" {
                $url = Read-Host "TheDiscDB URL"
                if ($url) {
                    $diskEpisodes = Get-DiskEpisodesFromDiscDb -DiscDbUrl $url -FirstEpisodeNumber 1 -AllSeasonEpisodes $episodes
                    $diskSource = "DiscDB (manual URL)"
                }
            }
            "2" {
                $diskEpisodes = Get-DiskEpisodesManually -AllSeasonEpisodes $episodes
                $diskSource = "Manual"
            }
            "3" {
                Write-Host "Proceeding with season-wide matching (no disk scoping)" -ForegroundColor Gray
                $diskSource = "Season (no disk scoping)"
            }
            default {
                Write-Host "Invalid choice. Proceeding with season-wide matching." -ForegroundColor Yellow
                $diskSource = "Season (no disk scoping)"
            }
        }
    }
}

# Use disk-specific episodes if available, otherwise use all season episodes
$episodesToMatch = if ($diskEpisodes -and $diskEpisodes.Count -gt 0) { $diskEpisodes } else { $episodes }

Write-Host ""
Write-Host "Matching strategy: $diskSource" -ForegroundColor Cyan
if ($diskEpisodes -and $diskEpisodes.Count -gt 0) {
    Write-Host "Scoped to $($diskEpisodes.Count) episodes (E$($diskEpisodes[0].episode_number)-E$($diskEpisodes[-1].episode_number))" -ForegroundColor Green
}
Write-Host ""

Write-Host "Analyzing ripped files..." -ForegroundColor Gray
$files = Get-ChildItem -Path $diskPath -File -Filter "*.mkv"

if ($files.Count -eq 0) {
    Write-Host "Error: No .mkv files found in $diskPath" -ForegroundColor Red
    exit 1
}

Write-Host "Found $($files.Count) files to process" -ForegroundColor Green

$fileInfos = @{}  # filename -> duration in seconds
$fileInfosMs = @{}  # filename -> duration with millisecond precision

foreach ($file in $files) {
    Write-Host "  Reading: $($file.Name)" -ForegroundColor Gray -NoNewline

    $durationMs = Get-FileDuration -FilePath $file.FullName -IncludeMs $true
    $duration = Get-FileDuration -FilePath $file.FullName -IncludeMs $false

    if ($duration) {
        $fileInfos[$file.Name] = $duration
        $fileInfosMs[$file.Name] = $durationMs
        $mins = [Math]::Floor($duration / 60)
        $secs = $duration % 60
        $ms = [Math]::Round(($durationMs - $duration) * 1000)
        Write-Host " ($mins`m $secs`s $ms`ms)" -ForegroundColor Green
    } else {
        Write-Host " (duration unknown - skipped)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Matching files to episodes by duration..." -ForegroundColor Gray

$result = Match-FilesToEpisodes -FileInfos $fileInfos -FileInfosMs $fileInfosMs -Episodes $episodesToMatch

Write-Host ""
Write-Host "Matches:" -ForegroundColor Cyan
foreach ($epNum in ($result.matches.Keys | Sort-Object)) {
    $episode = $episodes | Where-Object { $_.episode_number -eq $epNum }
    $fileName = $result.matches[$epNum]
    Write-Host "  E$('{0:D2}' -f $epNum): $($episode.name) -> $fileName" -ForegroundColor Green
}

if ($result.ambiguous.Count -gt 0) {
    Write-Host ""
    Write-Host "⚠ AMBIGUOUS MATCHES (manual verification recommended):" -ForegroundColor Yellow
    foreach ($item in $result.ambiguous) {
        Write-Host "  $item" -ForegroundColor Yellow
    }
}

if ($result.unmatched.Count -gt 0) {
    Write-Host ""
    Write-Host "Unmatched episodes (no file within tolerance):" -ForegroundColor Yellow
    foreach ($item in $result.unmatched) {
        Write-Host "  $item" -ForegroundColor Yellow
    }
}

Write-Host ""

$mapping = Build-Mapping -Matches $result.matches -Episodes $episodesToMatch -Season $Season -ShowName $Show

# Save mapping file
$mappingsDir = (Join-Path $baseDir $Show) | Join-Path -ChildPath "mappings"
if (-not (Test-Path $mappingsDir)) {
    New-Item -ItemType Directory -Path $mappingsDir -Force | Out-Null
}

$mappingFile = Join-Path $mappingsDir "S$('{0:D2}' -f $Season)D$('{0:D2}' -f $Disk).json"

$mapping | ConvertTo-Json | Set-Content -Path $mappingFile -Encoding utf8

Write-Host "Mapping saved to: $mappingFile" -ForegroundColor Green

if ($AutoRename) {
    Write-Host ""
    Write-Host "Auto-renaming files..." -ForegroundColor Gray

    foreach ($oldName in $mapping.Keys) {
        $oldPath = Join-Path $diskPath $oldName
        $newName = $mapping[$oldName]

        if (Test-Path $oldPath) {
            Rename-Item -Path $oldPath -NewName $newName
            Write-Host "  [OK] $oldName -> $newName" -ForegroundColor Green
        }
    }
}

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Complete. Run Rename-DiskRips.ps1 to apply mapping." -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""
