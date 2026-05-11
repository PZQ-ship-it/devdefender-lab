param(
    [string]$Owner = "PZQ-ship-it",
    [string]$Repo = "devdefender-lab"
)

$ErrorActionPreference = "Stop"

if (-not $env:GH_TOKEN) {
    throw "GH_TOKEN is required to create and push the GitHub repository."
}

$headers = @{
    Authorization = "Bearer $env:GH_TOKEN"
    Accept = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

$repoUrl = "https://github.com/$Owner/$Repo.git"
$apiUrl = "https://api.github.com/orgs/$Owner/repos"
$body = @{
    name = $Repo
    private = $false
    description = "Phase 1 integration lab for an AI code defense workflow."
} | ConvertTo-Json

try {
    Invoke-RestMethod -Method Post -Uri $apiUrl -Headers $headers -Body $body -ContentType "application/json" | Out-Null
    Write-Host "Created public repo: $repoUrl"
}
catch {
    $message = $_.ErrorDetails.Message
    if ($message -and $message.Contains("name already exists")) {
        Write-Host "Repo already exists: $repoUrl"
    }
    else {
        throw
    }
}

if (-not (git remote get-url origin 2>$null)) {
    git remote add origin $repoUrl
}
else {
    git remote set-url origin $repoUrl
}

git push -u origin main
