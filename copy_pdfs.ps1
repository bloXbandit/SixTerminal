# copy_pdfs.ps1
# Copies Schedule Validator PDFs from src/01 - Construction into copilot_web/projects/<slug>/
# Maps: "Schedule Compression" -> compression_updateN.pdf
#        "Variance Analysis"    -> variance_N.pdf
#        "All Activities"       -> verify_N.pdf
#        Prior All Activities   -> verify_{N-1}.pdf  (or verify_BL.pdf if current is Update 1)
# Run from repo root: .\copy_pdfs.ps1

$SrcRoot  = ".\src\01 - Construction"
$DstRoot  = ".\copilot_web\projects"

# Map: src folder prefix -> slug
$SlugMap = @{
    "01 - Colorado Springs, CO" = "colorado_springs_co"
    "02 - Fairfax, VA"          = "fairfax_va"
    "03 - Mt Juliet, TN"        = "mt_juliet_tn"
    "04 - Anaheim, CA"          = "anaheim_ca"
    "05 - Dallas, TX"           = "dallas_tx"
    "06 - Frisco, TX"           = "frisco_tx"
    "07 - Mesa, AZ"             = "mesa_az"
    "08 - San Diego, CA"        = "san_diego_ca"
    "09 - Davenport, FL"        = "davenport_fl"
    "10 - Anna, TX"             = "anna_tx"
    "11 - Willis, TX"           = "willis_tx"
    "12 - Aventura, FL"         = "aventura_fl"
    "13 - Delray, FL"           = "delray_fl"
    "14 - Selma, NC"            = "selma_nc"
    "15 - Meridian, ID"         = "meridian_id"
    "16 - Ocala, FL"            = "ocala_fl"
    "17 - Cocoa, FL"            = "cocoa_fl"
}

$copied  = 0
$skipped = 0
$errors  = 0

foreach ($projectFolder in Get-ChildItem -Path $SrcRoot -Directory) {
    $slug = $SlugMap[$projectFolder.Name]
    if (-not $slug) {
        Write-Host "  [SKIP] No slug mapping for '$($projectFolder.Name)'" -ForegroundColor Yellow
        continue
    }

    $dstDir = Join-Path $DstRoot $slug
    if (-not (Test-Path $dstDir)) {
        Write-Host "  [SKIP] Destination folder not found: $dstDir" -ForegroundColor Yellow
        continue
    }

    Write-Host "`n[$slug]" -ForegroundColor Cyan

    # Collect all update folder numbers first
    $updateNums = @()
    foreach ($updateFolder in Get-ChildItem -Path $projectFolder.FullName -Directory) {
        if ($updateFolder.Name -match 'Update\s*#(\d+)') {
            $updateNums += [int]$matches[1]
        }
    }

    # Each subfolder is an update: "Update #N" — copy standard PDFs
    foreach ($updateFolder in Get-ChildItem -Path $projectFolder.FullName -Directory) {
        if ($updateFolder.Name -match 'Update\s*#(\d+)') {
            $updateNum = $matches[1]
        } else {
            continue
        }

        foreach ($pdf in Get-ChildItem -Path $updateFolder.FullName -Filter "*.pdf") {
            $lower = $pdf.Name.ToLower()

            # Determine destination name
            if ($lower -like "schedule compression*") {
                $dstName = "compression_update$updateNum.pdf"
            } elseif ($lower -like "variance analysis*") {
                $dstName = "variance_$updateNum.pdf"
            } elseif ($lower -like "all activities*") {
                $dstName = "verify_$updateNum.pdf"
            } else {
                continue  # Dashboard, longest path, etc — skip
            }

            $dstPath = Join-Path $dstDir $dstName

            try {
                Copy-Item -Path $pdf.FullName -Destination $dstPath -Force
                Write-Host "  Copied Update #$updateNum : $($pdf.Name) -> $dstName" -ForegroundColor Green
                $copied++
            } catch {
                Write-Host "  [ERROR] $($pdf.FullName): $_" -ForegroundColor Red
                $errors++
            }
        }
    }

    # ── Prior verify logic ──────────────────────────────────────────────────
    # Find the highest (current) update number for this project
    if ($updateNums.Count -gt 0) {
        $currentNum = ($updateNums | Measure-Object -Maximum).Maximum

        if ($currentNum -eq 1) {
            # Current is Update 1 — prior is Baseline/
            $baselineDir = Join-Path $projectFolder.FullName "Baseline"
            if (Test-Path $baselineDir) {
                $blPdf = Get-ChildItem -Path $baselineDir -Filter "*.pdf" |
                         Where-Object { $_.Name.ToLower() -like "all activities*" } |
                         Select-Object -First 1
                if ($blPdf) {
                    $dstPath = Join-Path $dstDir "verify_BL.pdf"
                    if (-not (Test-Path $dstPath)) {
                        try {
                            Copy-Item -Path $blPdf.FullName -Destination $dstPath -Force
                            Write-Host "  Copied Baseline All Activities -> verify_BL.pdf" -ForegroundColor Green
                            $copied++
                        } catch {
                            Write-Host "  [ERROR] verify_BL: $_" -ForegroundColor Red
                            $errors++
                        }
                    } else {
                        Write-Host "  [SKIP] verify_BL.pdf already exists" -ForegroundColor DarkGray
                        $skipped++
                    }
                } else {
                    Write-Host "  [SKIP] No All Activities PDF found in Baseline/" -ForegroundColor DarkGray
                    $skipped++
                }
            }
        } else {
            # Current is Update N (N >= 2) — prior is Update #(N-1)/All Activities
            $priorNum  = $currentNum - 1
            # Handle folders named "Update #N" or "Update# N" (e.g. Selma uses "Update#1")
            $priorFolder = Get-ChildItem -Path $projectFolder.FullName -Directory |
                           Where-Object { $_.Name -match "Update\s*#\s*0*$priorNum\b" } |
                           Select-Object -First 1
            if ($priorFolder) {
                $priorPdf = Get-ChildItem -Path $priorFolder.FullName -Filter "*.pdf" |
                            Where-Object { $_.Name.ToLower() -like "all activities*" } |
                            Select-Object -First 1
                if ($priorPdf) {
                    $dstName = "verify_$priorNum.pdf"
                    $dstPath = Join-Path $dstDir $dstName
                    if (-not (Test-Path $dstPath)) {
                        try {
                            Copy-Item -Path $priorPdf.FullName -Destination $dstPath -Force
                            Write-Host "  Copied Update #$priorNum All Activities -> $dstName" -ForegroundColor Green
                            $copied++
                        } catch {
                            Write-Host "  [ERROR] $dstName : $_" -ForegroundColor Red
                            $errors++
                        }
                    } else {
                        Write-Host "  [SKIP] $dstName already exists" -ForegroundColor DarkGray
                        $skipped++
                    }
                } else {
                    Write-Host "  [SKIP] No All Activities PDF in Update #$priorNum" -ForegroundColor DarkGray
                    $skipped++
                }
            } else {
                Write-Host "  [SKIP] Update #$priorNum folder not found" -ForegroundColor DarkGray
                $skipped++
            }
        }
    }
}

Write-Host "`n--- Done: $copied copied, $skipped skipped, $errors errors ---" -ForegroundColor White
