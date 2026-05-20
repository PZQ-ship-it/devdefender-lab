param(
    [string]$CodexHome = $env:CODEX_HOME,
    [switch]$NoValidate
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Source = Join-Path $RepoRoot "skills\project-briefing-room"

if (-not $CodexHome) {
    $CodexHome = Join-Path $HOME ".codex"
}

$TargetRoot = Join-Path $CodexHome "skills"
$Target = Join-Path $TargetRoot "project-briefing-room"
$Validator = Join-Path $CodexHome "skills\.system\skill-creator\scripts\quick_validate.py"

if (-not (Test-Path (Join-Path $Source "SKILL.md"))) {
    throw "Source skill is missing: $Source"
}

New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
New-Item -ItemType Directory -Force -Path $Target | Out-Null

Get-ChildItem -Path $Source -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($Source.Length).TrimStart("\", "/")
    $destination = Join-Path $Target $relative
    $destinationDir = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
}

$validation = @{
    attempted = $false
    ok = $null
    message = $null
    validator = $Validator
}

if (-not $NoValidate) {
    if (Test-Path $Validator) {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $python) {
            $validation.ok = $false
            $validation.message = "python was not found on PATH; install completed but validation was skipped."
        }
        else {
            $validation.attempted = $true
            $process = Start-Process -FilePath $python.Source -ArgumentList @($Validator, $Target) -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$env:TEMP\project-briefing-room-skill-validate.out" -RedirectStandardError "$env:TEMP\project-briefing-room-skill-validate.err"
            $stdout = Get-Content "$env:TEMP\project-briefing-room-skill-validate.out" -Raw -ErrorAction SilentlyContinue
            $stderr = Get-Content "$env:TEMP\project-briefing-room-skill-validate.err" -Raw -ErrorAction SilentlyContinue
            $validation.ok = $process.ExitCode -eq 0
            $validation.message = (($stdout + " " + $stderr).Trim())
            if (-not $validation.ok) {
                throw "Skill validation failed: $($validation.message)"
            }
        }
    }
    else {
        $validation.message = "Validator not found; install completed without validation."
    }
}

$InvocationHint = 'Use $project-briefing-room to brief me and update the execution plan from my feedback.'

$report = @{
    ok = $true
    source = $Source
    target = $Target
    skill = "project-briefing-room"
    invocation = $InvocationHint
    validation = $validation
}

$report | ConvertTo-Json -Depth 5
