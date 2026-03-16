$runtimeRoot = Join-Path $env:LOCALAPPDATA 'PostgreSQL\portable-17\pgsql'
$dataDir = Join-Path $env:LOCALAPPDATA 'PostgreSQL\portable-17-data'
$pgCtl = Join-Path $runtimeRoot 'bin\pg_ctl.exe'

if (-not (Test-Path $pgCtl)) {
    Write-Error "Portable PostgreSQL was not found at $runtimeRoot"
    exit 1
}

& $pgCtl stop -D $dataDir -m fast
