param(
    [string]$Show,           # Show name (e.g., "Community")
    [int]$Season,            # Season number (optional, 1-based)
    [int]$Disk,              # Disk number (optional, 1-based)
    [switch]$WhatIf,         # Preview changes without renaming
    [switch]$MoveToCompleted # Move renamed files to completed folder after renaming
)

$baseDir = "D:\Disk Ripping"
$completedDir = "D:\Disk Ripping\Completed"
$TMDbApiKey = $env:TMDB_API_KEY

if (-not (Test-Path $baseDir)) {
    Write-Host "Error: Base directory not found: $baseDir" -ForegroundColor Red
    exit 1
}

function Get-TMDbShowYear {
    param([string]$ShowName, [string]$ApiKey)

    if (-not $ApiKey) {
        return $null
    }

    $url = "https://api.themoviedb.org/3/search/tv?api_key=$ApiKey&query=$([Uri]::EscapeDataString($ShowName))"

    try {
        $response = Invoke-RestMethod -Uri $url -ErrorAction Stop

        if ($response.results -and $response.results.Count -gt 0) {
            $show = $response.results[0]
            if ($show.first_air_date) {
                return [datetime]::ParseExact($show.first_air_date, "yyyy-MM-dd", $null).Year
            }
        }
    } catch {
        # Silently fail - year is optional
    }

    return $null
}

function Get-MappingFile {
    param([string]$ShowPath, [int]$Season, [int]$Disk)
    $mappingsDir = Join-Path $ShowPath "mappings"
    $mappingFile = Join-Path $mappingsDir "S$('{0:D2}' -f $Season)D$('{0:D2}' -f $Disk).json"
    return $mappingFile
}

function Load-Mappings {
    param([string]$MappingFile)

    if (-not (Test-Path $MappingFile)) {
        return $null
    }

    try {
        $json = Get-Content $MappingFile -Raw | ConvertFrom-Json

        if ($json.PSObject.Properties.Name -contains "episodes" -or $json.PSObject.Properties.Name -contains "bonus") {
            $mappings = @{}
            if ($json.episodes) {
                foreach ($item in $json.episodes) {
                    $mappings[$item.source] = $item.target
                }
            }
            if ($json.bonus) {
                foreach ($item in $json.bonus) {
                    $mappings[$item.source] = $item.target
                }
            }
            return $mappings
        } else {
            $mappings = @{}
            $json.PSObject.Properties | ForEach-Object {
                $mappings[$_.Name] = $_.Value
            }
            return $mappings
        }
    } catch {
        Write-Host "Error loading mapping file: $MappingFile" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        return $null
    }
}

function Rename-DiskFiles {
    param(
        [string]$DiskPath,
        [string]$ShowName,
        [int]$Season,
        [int]$DiskNum,
        [hashtable]$Mappings,
        [bool]$Preview,
        [string]$CompletedPath = $null
    )

    if (-not (Test-Path $DiskPath)) {
        return 0, 0, @()
    }

    $renamedCount = 0
    $skippedCount = 0
    $renamedFiles = @()

    $files = Get-ChildItem -Path $DiskPath -File
    if ($files.Count -eq 0) {
        return 0, 0, @()
    }

    foreach ($file in $files) {
        if ($Mappings.ContainsKey($file.Name)) {
            $newName = $Mappings[$file.Name]
            $oldPath = $file.FullName
            $newPath = Join-Path $DiskPath $newName

            if ($Preview) {
                Write-Host "  [PREVIEW] $($file.Name) -> $newName" -ForegroundColor Cyan
            } else {
                try {
                    Rename-Item -Path $oldPath -NewName $newName -ErrorAction Stop
                    Write-Host "  [OK] $($file.Name) -> $newName" -ForegroundColor Green
                    $renamedFiles += $newPath
                } catch {
                    Write-Host "  [FAIL] $($file.Name): $($_.Exception.Message)" -ForegroundColor Red
                }
            }
            $renamedCount++
        } else {
            $skippedCount++
        }
    }

    return $renamedCount, $skippedCount, $renamedFiles
}

function Process-Show {
    param(
        [string]$ShowPath,
        [string]$ShowName,
        [int]$TargetSeason,
        [int]$TargetDisk,
        [bool]$Preview,
        [string]$CompletedPath = $null
    )

    $seasonDirs = Get-ChildItem -Path $ShowPath -Directory | Where-Object { $_.Name -match "^Season\s+\d+" }

    if ($seasonDirs.Count -eq 0) {
        Write-Host "  No Season directories found in: $ShowPath" -ForegroundColor Yellow
        return 0, 0, @()
    }

    $totalRenamed = 0
    $totalSkipped = 0
    $allRenamedFiles = @()

    foreach ($seasonDir in $seasonDirs) {
        if ($seasonDir.Name -match "Season\s+(\d+)") {
            $seasonNum = [int]$matches[1]

            if ($TargetSeason -gt 0 -and $seasonNum -ne $TargetSeason) {
                continue
            }

            $diskDirs = Get-ChildItem -Path $seasonDir.FullName -Directory | Where-Object { $_.Name -match "^Disk\s+\d+" }

            foreach ($diskDir in $diskDirs) {
                if ($diskDir.Name -match "Disk\s+(\d+)") {
                    $diskNum = [int]$matches[1]

                    if ($TargetDisk -gt 0 -and $diskNum -ne $TargetDisk) {
                        continue
                    }

                    $mappingFile = Get-MappingFile -ShowPath $ShowPath -Season $seasonNum -Disk $diskNum
                    $mappings = Load-Mappings -MappingFile $mappingFile

                    if ($null -eq $mappings) {
                        Write-Host "  [SKIP] No mapping found: $mappingFile" -ForegroundColor Yellow
                        continue
                    }

                    Write-Host "  Season ${seasonNum} Disk ${diskNum}:" -ForegroundColor Gray
                    $renamed, $skipped, $renamedFiles = Rename-DiskFiles -DiskPath $diskDir.FullName -ShowName $ShowName -Season $seasonNum -DiskNum $diskNum -Mappings $mappings -Preview $Preview -CompletedPath $CompletedPath

                    $totalRenamed += $renamed
                    $totalSkipped += $skipped
                    $allRenamedFiles += $renamedFiles
                }
            }
        }
    }

    return $totalRenamed, $totalSkipped, $allRenamedFiles
}

Write-Host "`n" -NoNewline
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host "DISK RIPPING FILE RENAMER" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

if ($WhatIf) {
    Write-Host "[PREVIEW MODE - No files will be renamed]" -ForegroundColor Yellow
    Write-Host ""
}

if ($Show) {
    $showPath = Join-Path $baseDir $Show

    if (-not (Test-Path $showPath)) {
        Write-Host "Error: Show directory not found: $showPath" -ForegroundColor Red
        exit 1
    }

    Write-Host "Processing: $Show"
    if ($Season -gt 0) { Write-Host "  Season: $Season" }
    if ($Disk -gt 0) { Write-Host "  Disk: $Disk" }
    Write-Host ""

    $totalRenamed, $totalSkipped, $renamedFiles = Process-Show -ShowPath $showPath -ShowName $Show -TargetSeason $Season -TargetDisk $Disk -Preview $WhatIf -CompletedPath $completedDir
} else {
    $shows = Get-ChildItem -Path $baseDir -Directory | Where-Object { (Test-Path (Join-Path $_.FullName "mappings")) }

    if ($shows.Count -eq 0) {
        Write-Host "No shows with mappings found in: $baseDir" -ForegroundColor Yellow
        exit 0
    }

    Write-Host "Processing all shows:" -ForegroundColor Cyan
    Write-Host ""

    $totalRenamed = 0
    $totalSkipped = 0
    $renamedFiles = @()

    foreach ($showDir in $shows) {
        Write-Host "$($showDir.Name)" -ForegroundColor Cyan
        $renamed, $skipped, $renamed_files = Process-Show -ShowPath $showDir.FullName -ShowName $showDir.Name -TargetSeason 0 -TargetDisk 0 -Preview $WhatIf -CompletedPath $completedDir
        $totalRenamed += $renamed
        $totalSkipped += $skipped
        $renamedFiles += $renamed_files
        Write-Host ""
    }
}

if ($MoveToCompleted -and -not $WhatIf) {
    Write-Host ""
    Write-Host "Moving files to Completed folder..." -ForegroundColor Gray

    # Get show year for folder naming
    $showYear = Get-TMDbShowYear -ShowName $Show -ApiKey $TMDbApiKey
    $showFolderName = if ($showYear) { "$Show ($showYear)" } else { $Show }

    # Get all properly-named mkv files from all processed directories
    if ($Show) {
        $showPath = Join-Path $baseDir $Show
        $seasonDirs = Get-ChildItem -Path $showPath -Directory | Where-Object { $_.Name -match "^Season\s+(\d+)" }

        foreach ($seasonDir in $seasonDirs) {
            if ($seasonDir.Name -match "Season\s+(\d+)") {
                $seasonNum = $matches[1]

                if ($TargetSeason -gt 0 -and $seasonNum -ne $TargetSeason) {
                    continue
                }

                $diskDirs = Get-ChildItem -Path $seasonDir.FullName -Directory | Where-Object { $_.Name -match "^Disk\s+(\d+)" }

                foreach ($diskDir in $diskDirs) {
                    if ($TargetDisk -gt 0) {
                        if ($diskDir.Name -match "Disk\s+(\d+)") {
                            $diskNum = [int]$matches[1]
                            if ($diskNum -ne $TargetDisk) { continue }
                        }
                    }

                    $mkfiles = Get-ChildItem -Path $diskDir.FullName -Filter "*.mkv" -File

                    if ($mkfiles.Count -gt 0) {
                        $completedShowPath = Join-Path $completedDir $showFolderName
                        $completedSeasonPath = Join-Path $completedShowPath "Season $seasonNum"

                        if (-not (Test-Path $completedSeasonPath)) {
                            New-Item -ItemType Directory -Path $completedSeasonPath -Force | Out-Null
                        }

                        foreach ($file in $mkfiles) {
                            # Only move files that have proper naming (contain "S[NN]E[NN]")
                            if ($file.Name -match "S\d{2}E\d{2}") {
                                $destPath = Join-Path $completedSeasonPath $file.Name
                                Move-Item -Path $file.FullName -Destination $destPath -Force
                                Write-Host "  -> $($file.Name)" -ForegroundColor Green
                            }
                        }

                        # Remove empty disk directory
                        if ((Get-ChildItem -Path $diskDir.FullName | Measure-Object).Count -eq 0) {
                            Remove-Item -Path $diskDir.FullName -ErrorAction SilentlyContinue
                        }
                    }
                }
            }
        }
    }

    Write-Host ""
}

Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host "Summary: $totalRenamed renamed, $totalSkipped skipped" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""
