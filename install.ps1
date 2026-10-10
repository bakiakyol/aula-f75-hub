# Install / uninstall aula-f75-hub for the current user on Windows.
#   powershell -ExecutionPolicy Bypass -File install.ps1           install
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Remove   uninstall
# Nothing needs administrator rights: the folder goes on the user PATH and a
# shortcut goes in the user's Start menu.
param([switch]$Remove)
$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Shortcut = Join-Path ([Environment]::GetFolderPath("Programs")) "AULA F75.lnk"
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$Parts = @($UserPath -split ";" | Where-Object { $_ -ne "" })

if ($Remove) {
    $Kept = $Parts | Where-Object { $_.TrimEnd("\") -ne $Here.TrimEnd("\") }
    [Environment]::SetEnvironmentVariable("Path", ($Kept -join ";"), "User")
    if (Test-Path $Shortcut) { Remove-Item $Shortcut }
    Write-Host "Removed."
    exit 0
}

# Python for the command-line tool
$Py = Get-Command py -ErrorAction SilentlyContinue
if (-not $Py) { $Py = Get-Command python -ErrorAction SilentlyContinue }
if (-not $Py) {
    Write-Host "Python 3.10+ is needed: winget install Python.Python.3.12 (or python.org), then run this again."
    exit 1
}
Write-Host "Python: $($Py.Source)"

# The folder on the user PATH, so 'aula' works in new terminals
if (-not ($Parts | Where-Object { $_.TrimEnd("\") -eq $Here.TrimEnd("\") })) {
    [Environment]::SetEnvironmentVariable("Path", (($Parts + $Here) -join ";"), "User")
    Write-Host "Added $Here to your PATH (open a new terminal to use 'aula')."
}

# Start menu shortcut for the GUI
$Shell = New-Object -ComObject WScript.Shell
$Link = $Shell.CreateShortcut($Shortcut)
$Link.TargetPath = Join-Path $Here "aula-gui.cmd"
$Link.WorkingDirectory = $Here
$Link.WindowStyle = 7   # minimized: the console window of the .cmd stays out of the way
$Link.Description = "AULA F75 keyboard settings"
$Link.Save()
Write-Host "Added 'AULA F75' to the Start menu."

# Is the GUI ready? It needs MSYS2's Python with GTK 3.
$Msys = if ($env:AULA_MSYS2) { $env:AULA_MSYS2 } else { "C:\msys64" }
$GuiPy = Join-Path $Msys "ucrt64\bin\python.exe"
$GuiReady = $false
if (Test-Path $GuiPy) {
    $env:Path = (Join-Path $Msys "ucrt64\bin") + ";" + $env:Path
    try {
        # stderr of a native program counts as an error in Windows PowerShell; don't stop on it
        $ErrorActionPreference = "Continue"
        & $GuiPy -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>$null | Out-Null
        $GuiReady = ($LASTEXITCODE -eq 0)
    } catch {
        $GuiReady = $false
    } finally {
        $ErrorActionPreference = "Stop"
    }
}
if ($GuiReady) {
    Write-Host "GUI: ready ($GuiPy)."
} else {
    Write-Host "GUI: not ready yet. The command-line tool works without it."
    Write-Host "  1. winget install MSYS2.MSYS2"
    Write-Host "  2. In the 'MSYS2 UCRT64' terminal:"
    Write-Host "     pacman -S --needed mingw-w64-ucrt-x86_64-gtk3 mingw-w64-ucrt-x86_64-python-gobject"
    Write-Host "  See docs\windows.md for details."
}
Write-Host "Installed. Try: aula devices"
