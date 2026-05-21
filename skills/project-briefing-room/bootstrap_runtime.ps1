param(
    [string]$InstallRoot = (Join-Path $HOME ".codex\runtime"),
    [string]$RepoUrl = "https://github.com/PZQ-ship-it/devdefender-lab.git",
    [string]$Ref = "main",
    [string]$Python = "python",
    [switch]$SkipDoctor
)

$ErrorActionPreference = "Stop"

if ($RepoUrl -ne "https://github.com/PZQ-ship-it/devdefender-lab.git") {
    throw "Refusing untrusted runtime repo: $RepoUrl"
}

$RuntimeRoot = Join-Path $InstallRoot "devdefender-lab"
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null

if (Test-Path (Join-Path $RuntimeRoot ".git")) {
    git -C $RuntimeRoot fetch --depth 1 origin $Ref
    git -C $RuntimeRoot checkout FETCH_HEAD
}
else {
    if (Test-Path $RuntimeRoot) {
        throw "Runtime path exists but is not a git checkout: $RuntimeRoot"
    }
    git clone --depth 1 --branch $Ref $RepoUrl $RuntimeRoot
}

& $Python -m pip install -e $RuntimeRoot

$doctor = @{
    skipped = $true
    ok = $null
}

if (-not $SkipDoctor) {
    & $Python -m devdefender_lab.cli project-briefing-room-doctor --out (Join-Path $RuntimeRoot "artifacts\project_briefing_room_doctor.json")
    $doctor.skipped = $false
    $doctor.ok = $LASTEXITCODE -eq 0
    if (-not $doctor.ok) {
        throw "Project Briefing Room doctor failed after runtime bootstrap."
    }
}

@{
    ok = $true
    runtime_root = $RuntimeRoot
    repo_url = $RepoUrl
    ref = $Ref
    doctor = $doctor
    commands = @(
        "project-briefing-room",
        "project-briefing-room-doctor",
        "project-briefing-agent-input"
    )
} | ConvertTo-Json -Depth 5
