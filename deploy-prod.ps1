# Sync iBistro to Prod VPS and run scripts/after-deploy.sh.
$ErrorActionPreference = "Stop"

$Remote = "root@38.247.128.114"
$RemotePath = "/root/code/ibistro/app"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $RepoRoot ".envprod"

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Missing .envprod in $RepoRoot."
}
$confirm = Read-Host "Deploy iBistro to PRODUCTION ($Remote)? Type YES to continue"
if ($confirm -ne "YES") { throw "Aborted." }

if (-not (Get-Command wsl -ErrorAction SilentlyContinue)) {
    throw "WSL is required."
}

$RepoUnix = ($RepoRoot -replace "\\", "/")
$WslRepo = (& wsl wslpath -a $RepoUnix).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($WslRepo)) {
    throw "Could not convert repo path to WSL via wslpath: $RepoRoot"
}

Write-Host "==> [Prod] mkdir ${Remote}:${RemotePath}" -ForegroundColor Cyan
& wsl ssh -o StrictHostKeyChecking=no $Remote "mkdir -p ${RemotePath}"
if ($LASTEXITCODE -ne 0) {
    throw "Remote mkdir failed (exit $LASTEXITCODE)."
}

Write-Host "==> [Prod] rsync -> ${Remote}:${RemotePath}/" -ForegroundColor Cyan
& wsl rsync -av --delete --filter=":- .gitignore" `
    --exclude ".env" `
    --exclude ".venv" `
    --exclude "node_modules" `
    --exclude ".git" `
    --exclude "compose.override.yml" `
    -e "ssh -o StrictHostKeyChecking=no" `
    "${WslRepo}/" `
    "${Remote}:${RemotePath}/"
if ($LASTEXITCODE -ne 0) {
    $code = $LASTEXITCODE
    Write-Host "HINT: rsync exit $code — often I/O (11): bad WSL path, missing remote dir, disk full, or locked files." -ForegroundColor Yellow
    throw "rsync failed (exit $code)."
}

Write-Host "==> [Prod] after-deploy.sh" -ForegroundColor Cyan
& wsl ssh -o StrictHostKeyChecking=no $Remote "cd ${RemotePath} && sed -i 's/\r`$//' scripts/*.sh backend/scripts/*.sh && bash scripts/after-deploy.sh"
if ($LASTEXITCODE -ne 0) {
    throw "after-deploy.sh failed (exit $LASTEXITCODE)."
}

Write-Host "==> iBistro Prod deploy finished." -ForegroundColor Green
