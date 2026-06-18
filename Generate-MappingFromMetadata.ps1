param(
    [Parameter(Mandatory=$true)]
    [string]$Show,

    [Parameter(Mandatory=$true)]
    [int]$Season,

    [int]$Disk = 1,

    [string]$TMDbApiKey,

    [switch]$AutoRename,

    [string]$EpisodeRange,

    [string]$DiscDbUrl
)

$baseDir = "D:\Disk Ripping"

if (-not $TMDbApiKey) {
    $TMDbApiKey = $env:TMDB_API_KEY
}

if (-not $TMDbApiKey) {
    Write-Host "Error: TMDb API key required" -ForegroundColor Red
    exit 1
}

function Get-FileDuration {
    param([string]$FilePath, [bool]$IncludeMs = $false)

    $ffprobe = (Get-Command ffprobe -ErrorAction SilentlyContinue).Source

    if ($ffprobe) {
        try {
            $json = & ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1:nokey=1 "$FilePath" 2>$null
            if ($json) {
                $durationSecs = [double]$json
                if ($IncludeMs) {
                    return $durationSecs
                } else {
                    return [int]$durationSecs
                }
            }
        } catch {
            # Fall through
        }
    }

    try {
        $shell = New-Object -ComObject Shell.Application
        $folder = $shell.Namespace((Split-Path $FilePath))
        $file = $folder.ParseName((Split-Path $FilePath -Leaf))
        $duration = $file.ExtendedProperty("System.Media.Duration")

        if ($duration) {
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

function Invoke-DiscDbAutoDiscovery {
    param(
        [string]$ShowName,
        [int]$Season,
        [int]$Disk
    )

    Write-Host "Attempting to auto-discover TheDiscDB URL..." -ForegroundColor Gray

    $showSlug = $ShowName.ToLower() -replace '\s+', '-'
    $diskNum = $Disk.ToString("D2")
    $seasonNum = $Season.ToString("D2")

    $patterns = @(
        "https://thediscdb.com/series/$showSlug-2009/releases/2018-complete-series-blu-ray/discs/s$($seasonNum)d$($diskNum)",
        "https://thediscdb.com/series/$showSlug/releases/2018-complete-series-blu-ray/discs/s$($seasonNum)d$($diskNum)",
        "https://thediscdb.com/series/$showSlug/releases/complete-series-blu-ray/discs/s$($seasonNum)d$($diskNum)"
    )

    foreach ($url in $patterns) {
        try {
            $response = Invoke-WebRequest -Uri $url -ErrorAction SilentlyContinue -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                Write-Host "Found: $url" -ForegroundColor Green
                return $url
            }
        } catch {
            # Continue to next pattern
        }
    }

    return $null
}

function Get-DiscDbEpisodeList {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -Uri $Url -ErrorAction Stop
        $content = $response.Content

        $matches = [regex]::Matches($content, '"([^"]+)"')
        if ($matches.Count -gt 0) {
            $titles = @()
            foreach ($match in $matches) {
                $titles += $match.Groups[1].Value
            }
            return $titles
        }
    } catch {
        Write-Host "Error fetching DiscDB: $($_.Exception.Message)" -ForegroundColor Red
    }

    return $null
}


function Match-FilesToEpisodes {
    param(
        [hashtable]$FileInfos,
        [hashtable]$FileInfosMs,
        [array]$Episodes
    )

    $matches = @{}
    $unmatched = @()
    $ambiguous = @()
    $tolerance = 90
    $matchedFiles = @()

    foreach ($episode in $Episodes) {
        $episodeRuntime = $episode.runtime * 60
        $bestMatch = $null
        $bestDiff = $tolerance + 1
        $matchesWithinTolerance = @()

        foreach ($fileName in $FileInfos.Keys) {
            if ($matchedFiles -contains $fileName) {
                continue
            }

            $fileDuration = $FileInfos[$fileName]
            $diff = [Math]::Abs($fileDuration - $episodeRuntime)

            if ($diff -lt $bestDiff) {
                $bestMatch = $fileName
                $bestDiff = $diff
            }

            if ($diff -le $tolerance) {
                $matchesWithinTolerance += @{ file = $fileName; diff = $diff; duration = $fileDuration; durationMs = $FileInfosMs[$fileName] }
            }
        }

        if ($bestMatch -and $bestDiff -le $tolerance) {
            $identicalDurationFiles = $matchesWithinTolerance | Where-Object { [Math]::Abs($_.diff - $bestDiff) -lt 0.01 }

            if ($identicalDurationFiles.Count -gt 1) {
                $ambiguousEp = "E$('{0:D2}' -f $episode.episode_number): $($episode.name) - MULTIPLE FILES WITH SAME DURATION:"
                foreach ($match in $identicalDurationFiles) {
                    $ambiguousEp += "`n    | $($match.file): $([Math]::Round($match.durationMs, 3))s"
                }
                $ambiguous += $ambiguousEp
            }

            $matches[$episode.episode_number] = $bestMatch
            $matchedFiles += $bestMatch
        } else {
            $unmatched += "E$('{0:D2}' -f $episode.episode_number): Runtime $episodeRuntime`s (no file within $tolerance`s tolerance)"
        }
    }

    return @{ matches = $matches; unmatched = $unmatched; ambiguous = $ambiguous }
}

function Build-Mapping {
    param(
        [hashtable]$Matches,
        [array]$Episodes,
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

            foreach ($char in @('<', '>', ':', '"', '/', '\', '|', '?', '*')) {
                $newName = $newName.Replace($char, '-')
            }

            $mapping[$fileName] = $newName
        }
    }

    return $mapping
}

# Main execution
Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "TMDB-BASED MAPPING GENERATOR" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
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

$allEpisodes = Get-TMDbEpisodes -ShowId $showId -Season $Season

if (-not $allEpisodes) {
    Write-Host "Error: Could not fetch episodes for Season $Season" -ForegroundColor Red
    exit 1
}

Write-Host "Found $($allEpisodes.Count) episodes on TMDb for Season $Season" -ForegroundColor Green
Write-Host ""

Write-Host "Analyzing ripped files..." -ForegroundColor Gray
$files = Get-ChildItem -Path $diskPath -File -Filter "*.mkv"

if ($files.Count -eq 0) {
    Write-Host "Error: No .mkv files found in $diskPath" -ForegroundColor Red
    exit 1
}

Write-Host "Found $($files.Count) files to process" -ForegroundColor Green

$fileInfos = @{}
$fileInfosMs = @{}

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

# TIER 1: Try auto-discovery
$episodesToMatch = $allEpisodes
$matchSource = "Season-wide"
$discDbUrlResolved = $null

if (-not $DiscDbUrl) {
    $discDbUrlResolved = Invoke-DiscDbAutoDiscovery -ShowName $Show -Season $Season -Disk $Disk
}

if ($discDbUrlResolved) {
    # TIER 1 success: auto-discovered URL
    $titles = Get-DiscDbEpisodeList -Url $discDbUrlResolved
    if ($titles -and $titles.Count -eq $files.Count) {
        $matchSource = "DiscDB (auto-discovered)"
        Write-Host "Using episodes from TheDiscDB ($($titles.Count) episodes)" -ForegroundColor Green
        Write-Host ""
    }
} elseif ($DiscDbUrl) {
    # TIER 2: Manual DiscDB URL provided
    Write-Host "Using provided TheDiscDB URL..." -ForegroundColor Gray
    $titles = Get-DiscDbEpisodeList -Url $DiscDbUrl
    if ($titles) {
        $matchSource = "DiscDB (manual URL)"
        Write-Host "Using episodes from TheDiscDB ($($titles.Count) episodes)" -ForegroundColor Green
        Write-Host ""
    } else {
        Write-Host "Error: Could not fetch episodes from provided DiscDB URL: $DiscDbUrl" -ForegroundColor Red
        exit 1
    }
} elseif ($EpisodeRange) {
    # TIER 2: Manual episode range provided
    if ($EpisodeRange -match '^(\d+)-(\d+)$') {
        $start = [int]$matches[1]
        $end = [int]$matches[2]
        $episodesToMatch = $allEpisodes | Where-Object { $_.episode_number -ge $start -and $_.episode_number -le $end }

        if ($episodesToMatch.Count -eq 0) {
            Write-Host "Error: No episodes found in range $EpisodeRange for Season $Season" -ForegroundColor Red
            exit 1
        }

        $matchSource = "Manual range ($start-$end)"
        Write-Host "Scoped to episodes $start-$end" -ForegroundColor Green
        Write-Host ""
    } else {
        Write-Host "Error: Invalid episode range format: $EpisodeRange" -ForegroundColor Red
        Write-Host "Expected format: -EpisodeRange ""14-25""" -ForegroundColor Yellow
        exit 1
    }
} else {
    # TIER 3: No parameters provided and auto-discovery failed
    Write-Host ""
    Write-Host "Error: Could not auto-discover TheDiscDB entry." -ForegroundColor Red
    Write-Host ""
    Write-Host "Please provide one of the following parameters:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  -DiscDbUrl ""<URL>""" -ForegroundColor Cyan
    Write-Host "    Example: -DiscDbUrl ""https://thediscdb.com/series/breaking-bad/releases/...discs/s01d01""" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  -EpisodeRange ""<start>-<end>""" -ForegroundColor Cyan
    Write-Host "    Example: -EpisodeRange ""14-25""" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Full command example:" -ForegroundColor Yellow
    Write-Host "  .\Generate-MappingFromMetadata.ps1 -Show ""Breaking Bad"" -Season 1 -Disk 1 -EpisodeRange ""1-7""" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

Write-Host "Matching files to episodes by duration..." -ForegroundColor Gray
Write-Host "Strategy: $matchSource" -ForegroundColor Cyan
Write-Host ""

$result = Match-FilesToEpisodes -FileInfos $fileInfos -FileInfosMs $fileInfosMs -Episodes $episodesToMatch

Write-Host "Matches:" -ForegroundColor Cyan
foreach ($epNum in ($result.matches.Keys | Sort-Object)) {
    $episode = $episodesToMatch | Where-Object { $_.episode_number -eq $epNum }
    $fileName = $result.matches[$epNum]
    Write-Host "  E$('{0:D2}' -f $epNum): $($episode.name) -> $fileName" -ForegroundColor Green
}

if ($result.ambiguous.Count -gt 0) {
    Write-Host ""
    Write-Host "WARNING: AMBIGUOUS MATCHES (manual verification recommended):" -ForegroundColor Yellow
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
        $newPath = Join-Path $diskPath $newName

        if (Test-Path $oldPath) {
            Move-Item -Path $oldPath -Destination $newPath -Force
            Write-Host "  [OK] $oldName -> $newName" -ForegroundColor Green
        }
    }
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Complete. Run Rename-DiskRips.ps1 to apply mapping." -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""
