# copy_prior_verify.ps1
# Copies prior-update "All Activities" PDFs into project folders as verify_BL.pdf or verify_{N-1}.pdf
# Run from repo root: powershell -ExecutionPolicy Bypass -File copy_prior_verify.ps1

$SrcRoot = ".\src\01 - Construction"
$DstRoot = ".\copilot_web\projects"

$SlugMap = @{
    "01 - Colorado Springs, CO" = "colorado_springs_co"
    "02 - Fairfax, VA"          = "fairfax_va"
    "03 - Mt Juliet, TN"        = "mt_juliet_tn"
    "04 - Anaheim, CA"          = "anaheim_ca"
    "06 - Frisco, TX"           = "frisco_tx"
    "07 - Mesa, AZ"             = "mesa_az"
    "09 - Davenport, FL"        = "davenport_fl"
    "10 - Anna, TX"             = "anna_tx"
    "11 - Willis, TX"           = "willis_tx"
    "12 - Aventura, FL"         = "aventura_fl"
    "13 - Delray, FL"           = "delray_fl"
    "14 - Selma, NC"            = "selma_nc"
    "15 - Meridian, ID"         = "meridian_id"
}

$copied  = 0
$skipped = 0

foreach ($pf in Get-ChildItem -Path $SrcRoot -Directory) {
    $slug = $SlugMap[$pf.Name]
    if (-not $slug) { continue }

    $dstDir = Join-Path $DstRoot $slug
    if (-not (Test-Path $dstDir)) {
        Write-Host "  [SKIP] Destination not found: $dstDir" -ForegroundColor Yellow
        continue
    }

    Write-Host "`n[$slug]" -ForegroundColor Cyan

    # Collect update numbers
    $updateNums = @()
    foreach ($uf in Get-ChildItem -Path $pf.FullName -Directory) {
        if ($uf.Name -match 'Update\s*#\s*(\d+)') {
            $updateNums += [int]$matches[1]
        }
    }
    if ($updateNums.Count -eq 0) {
        Write-Host "  [SKIP] No update folders found" -ForegroundColor DarkGray
        continue
    }

    $curr = ($updateNums | Measure-Object -Maximum).Maximum

    if ($curr -eq 1) {
        # Update 1 — prior is Baseline/All Activities
        $blDir = Join-Path $pf.FullName "Baseline"
        if (Test-Path $blDir) {
            $blPdf = Get-ChildItem -Path $blDir -Filter "*.pdf" |
                     Where-Object { $_.Name -like "All Activities*" } |
                     Select-Object -First 1
            if ($blPdf) {
                $dst = Join-Path $dstDir "verify_BL.pdf"
                if (-not (Test-Path $dst)) {
                    Copy-Item $blPdf.FullName $dst -Force
                    Write-Host "  Copied verify_BL.pdf <- $($blPdf.Name)" -ForegroundColor Green
                    $copied++
                } else {
                    Write-Host "  [SKIP] verify_BL.pdf already exists" -ForegroundColor DarkGray
                    $skipped++
                }
            } else {
                Write-Host "  [SKIP] No All Activities PDF in Baseline/" -ForegroundColor DarkGray
            }
        } else {
            Write-Host "  [SKIP] No Baseline/ folder found" -ForegroundColor DarkGray
        }
    } else {
        # Update N (N>=2) — prior is Update #(N-1)/All Activities
        $prior = $curr - 1
        $priorFolder = Get-ChildItem -Path $pf.FullName -Directory |
                       Where-Object { $_.Name -match "Update\s*#\s*0*${prior}\b" } |
                       Select-Object -First 1
        if ($priorFolder) {
            $priorPdf = Get-ChildItem -Path $priorFolder.FullName -Filter "*.pdf" |
                        Where-Object { $_.Name -like "All Activities*" } |
                        Select-Object -First 1
            if ($priorPdf) {
                $dstName = "verify_${prior}.pdf"
                $dst = Join-Path $dstDir $dstName
                if (-not (Test-Path $dst)) {
                    Copy-Item $priorPdf.FullName $dst -Force
                    Write-Host "  Copied $dstName <- $($priorPdf.Name)" -ForegroundColor Green
                    $copied++
                } else {
                    Write-Host "  [SKIP] $dstName already exists" -ForegroundColor DarkGray
                    $skipped++
                }
            } else {
                Write-Host "  [SKIP] No All Activities PDF in Update #$prior" -ForegroundColor DarkGray
            }
        } else {
            Write-Host "  [SKIP] Update #$prior folder not found" -ForegroundColor DarkGray
        }
    }
}

Write-Host "`n--- Done: $copied copied, $skipped skipped ---" -ForegroundColor White
