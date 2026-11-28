# Sync iBistro to Test VPS and run scripts/after-deploy-test.sh.
$ErrorActionPreference = "Stop"

$Remote = "root@108.181.187.202"
$RemotePath = "/root/code/ibistro/app"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $RepoRoot ".envtest"

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Missing .envtest in $RepoRoot."
}
if (-not (Get-Command wsl -ErrorAction SilentlyContinue)) {
    throw "WSL is required."
}

$RepoUnix = $RepoRoot.Replace("\", "/")
$drive = $RepoUnix.Substring(0, 1).ToLower()
$pathWithoutDrive = $RepoUnix.Substring(2)
$WslRepo = "/mnt/$drive$pathWithoutDrive"

if ([string]::IsNullOrWhiteSpace($WslRepo)) {
    throw "Could not convert repo path to WSL: $RepoRoot"
}

Write-Host "==> [Test] mkdir ${Remote}:${RemotePath}" -ForegroundColor Cyan
& wsl ssh -o StrictHostKeyChecking=no $Remote "mkdir -p ${RemotePath}"
if ($LASTEXITCODE -ne 0) {
    throw "Remote mkdir failed (exit $LASTEXITCODE)."
}

Write-Host "==> [Test] rsync -> ${Remote}:${RemotePath}/" -ForegroundColor Cyan
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

Write-Host "==> [Test] after-deploy-test.sh" -ForegroundColor Cyan
& wsl ssh -o StrictHostKeyChecking=no $Remote "cd ${RemotePath} && sed -i 's/\r`$//' scripts/*.sh backend/scripts/*.sh && bash scripts/after-deploy-test.sh"
if ($LASTEXITCODE -ne 0) {
    throw "after-deploy-test.sh failed (exit $LASTEXITCODE)."
}

Write-Host "==> iBistro Test deploy finished." -ForegroundColor Green
