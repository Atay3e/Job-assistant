param(
  [switch]$Open
)

$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HostName = "127.0.0.1"
$Port = 8787
$Url = "http://$HostName`:$Port/"
$ApiUrl = "${Url}api/summary"
$LogDir = Join-Path $AppDir "logs"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Write-LauncherLog {
  param([string]$Message)
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path (Join-Path $LogDir "launcher.log") -Value $line -Encoding UTF8
}

function Test-JobAssistant {
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $ApiUrl -TimeoutSec 4 | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Get-PythonPath {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python -and $python.Source) {
    return $python.Source
  }
  throw "Cannot find python on PATH."
}

function Test-PythonDependencies {
  param([string]$PythonPath)
  $checkScript = "import importlib.util, sys; missing=[name for name in ['bs4','playwright','reportlab','fitz','requests','docx'] if importlib.util.find_spec(name) is None]; print(', '.join(missing)); sys.exit(1 if missing else 0)"
  $output = & $PythonPath -c $checkScript 2>&1
  if ($LASTEXITCODE -ne 0) {
    $message = "Missing optional Python packages: $output. Install with: python -m pip install -r requirements.txt; then run: python -m playwright install chromium"
    Write-LauncherLog $message
    Write-Host $message
  }
}

if (-not (Test-JobAssistant)) {
  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($listener) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $commandLine = $process.CommandLine
    if ($commandLine -notmatch "server\.py") {
      Write-LauncherLog "Port $Port is already used by process $($listener.OwningProcess): $commandLine"
      throw "Port $Port is already in use by another process."
    }
  }

  $pythonPath = Get-PythonPath
  Test-PythonDependencies -PythonPath $pythonPath
  $stdout = Join-Path $LogDir "server.out.log"
  $stderr = Join-Path $LogDir "server.err.log"

  Write-LauncherLog "Starting Job Assistant with $pythonPath"
  Start-Process `
    -FilePath $pythonPath `
    -ArgumentList "server.py" `
    -WorkingDirectory $AppDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr

  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Test-JobAssistant) {
      Write-LauncherLog "Job Assistant is ready at $Url"
      break
    }
  }
}

if (-not (Test-JobAssistant)) {
  Write-LauncherLog "Failed to start Job Assistant."
  throw "Job Assistant did not become ready. Check logs\server.err.log."
}

if ($Open) {
  Start-Process $Url
}
