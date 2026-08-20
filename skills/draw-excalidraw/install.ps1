$ErrorActionPreference = "Stop"
$Src = Split-Path -Parent $MyInvocation.MyCommand.Path
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $HOME ".dsh" }
$Dest = Join-Path $DshHome "skills/draw-excalidraw"
Write-Host "[draw-excalidraw] installing to $Dest"
New-Item -ItemType Directory -Force -Path (Join-Path $DshHome "skills") | Out-Null
if ((Resolve-Path $Src).Path -ne $Dest) {
  if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
  Copy-Item -Recurse -Force $Src $Dest
}
Push-Location $Dest
try {
  npm install --omit=dev --no-audit --no-fund
  node scripts/draw.mjs doctor
} finally { Pop-Location }
Write-Host "Installed: $Dest"
