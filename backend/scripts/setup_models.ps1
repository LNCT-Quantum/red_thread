[CmdletBinding()]
param(
    [string]$ModelName = "qwen2.5:3b-instruct-q4_K_M",
    [string]$BaseUrl = "http://127.0.0.1:11434",
    [switch]$SkipModelPull,
    [switch]$RequireQ4KM
)

$ErrorActionPreference = "Stop"
Write-Host "=== Red Thread: Local LLM Setup ===" -ForegroundColor Cyan
Write-Host "Runtime: Ollama"
Write-Host "Model:   $ModelName"
Write-Host "API:     $BaseUrl"

# This component is local-only. Refuse non-loopback API addresses.
$parsedBaseUrl = $null
if (-not [System.Uri]::TryCreate($BaseUrl, [System.UriKind]::Absolute, [ref]$parsedBaseUrl) -or
    $parsedBaseUrl.Scheme -ne "http" -or
    $parsedBaseUrl.Host -notin @("127.0.0.1", "localhost", "::1")) {
    Write-Host "ERROR: BaseUrl must be a local loopback URL (127.0.0.1, localhost, or ::1)." -ForegroundColor Red
    exit 1
}

# 1. Confirm the Ollama CLI exists and returns a version.
Write-Host "`n[1/5] Checking Ollama installation..." -ForegroundColor Cyan
$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollamaCommand) {
    Write-Host "ERROR: Ollama was not found in PATH. Install Ollama for Windows and reopen PowerShell." -ForegroundColor Red
    exit 1
}
$versionOutput = & ollama --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: 'ollama --version' failed." -ForegroundColor Red
    exit 1
}
Write-Host "OK: $versionOutput" -ForegroundColor Green

# 2. Confirm that the local API is ready.
Write-Host "`n[2/5] Checking local Ollama API..." -ForegroundColor Cyan
try {
    $null = Invoke-RestMethod -Uri "$BaseUrl/api/tags" -Method Get -TimeoutSec 5
    Write-Host "OK: local Ollama API is responding." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Ollama API is not ready at $BaseUrl." -ForegroundColor Red
    Write-Host "Start the Ollama application, then run this script again." -ForegroundColor Yellow
    exit 1
}

# 3. Pull the requested model only when it is not already installed.
Write-Host "`n[3/5] Checking model availability..." -ForegroundColor Cyan
$modelList = (& ollama list | Out-String)
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: 'ollama list' failed." -ForegroundColor Red
    exit 1
}
if ($modelList -notmatch [regex]::Escape($ModelName)) {
    if ($SkipModelPull) {
        Write-Host "ERROR: Model '$ModelName' is missing and -SkipModelPull was specified." -ForegroundColor Red
        exit 1
    }
    Write-Host "Model not found. Pulling '$ModelName'. Internet access is needed only for this first download." -ForegroundColor Yellow
    & ollama pull $ModelName
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Model download failed. Check the Ollama log and available disk space." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "OK: model is already installed." -ForegroundColor Green
}

# 4. Verify that the model is listed after the pull/check.
Write-Host "`n[4/5] Verifying installed model list..." -ForegroundColor Cyan
$modelList = (& ollama list | Out-String)
if ($LASTEXITCODE -ne 0 -or $modelList -notmatch [regex]::Escape($ModelName)) {
    Write-Host "ERROR: Model '$ModelName' is still not visible after setup." -ForegroundColor Red
    exit 1
}
Write-Host "OK: model is present in 'ollama list'." -ForegroundColor Green

# 5. Read model metadata. Do not silently claim Q4_K_M if metadata says otherwise.
Write-Host "`n[5/5] Checking model metadata..." -ForegroundColor Cyan
$body = @{ model = $ModelName } | ConvertTo-Json -Compress
try {
    $show = Invoke-RestMethod -Uri "$BaseUrl/api/show" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 15
    $quantization = $show.details.quantization_level
    $parameterSize = $show.details.parameter_size
    Write-Host "Parameter size: $parameterSize"
    Write-Host "Quantization:   $quantization"
    if ($quantization -ne "Q4_K_M") {
        $message = "WARNING: Installed model quantization is '$quantization', not the required Q4_K_M. Verify the tag or use the exact Q4_K_M GGUF with llama.cpp."
        if ($RequireQ4KM) {
            Write-Host $message -ForegroundColor Red
            exit 1
        }
        Write-Host $message -ForegroundColor Yellow
    } else {
        Write-Host "OK: Q4_K_M metadata confirmed." -ForegroundColor Green
    }
} catch {
    Write-Host "WARNING: Could not read model metadata: $($_.Exception.Message)" -ForegroundColor Yellow
    if ($RequireQ4KM) { exit 1 }
}

Write-Host "`n=== Setup checks completed ===" -ForegroundColor Cyan
Write-Host 'Next: create/activate your Python environment, install requirements, and run: python -c "from engine_runner import initialize_engine; print(initialize_engine())"'
