@echo off
setlocal EnableExtensions

set "SOURCE="
set "TARGET="
set "PID="
set "RESTART="

:parse
if "%~1"=="" goto validate
if /I "%~1"=="--source" (
    set "SOURCE=%~2"
    shift
    shift
    goto parse
)
if /I "%~1"=="--target" (
    set "TARGET=%~2"
    shift
    shift
    goto parse
)
if /I "%~1"=="--pid" (
    set "PID=%~2"
    shift
    shift
    goto parse
)
if /I "%~1"=="--restart" (
    set "RESTART=%~2"
    shift
    shift
    goto parse
)
echo Unknown argument: %~1
exit /b 2

:validate
if "%SOURCE%"=="" (
    echo Missing --source
    exit /b 2
)
if "%TARGET%"=="" (
    echo Missing --target
    exit /b 2
)
if "%PID%"=="" (
    echo Missing --pid
    exit /b 2
)
if "%RESTART%"=="" (
    echo Missing --restart
    exit /b 2
)
if not exist "%SOURCE%\" (
    echo Source directory does not exist: %SOURCE%
    exit /b 3
)
if not exist "%TARGET%\" (
    echo Target directory does not exist: %TARGET%
    exit /b 3
)
if not exist "%SOURCE%\Aura.exe" (
    echo Source is missing Aura.exe: %SOURCE%
    exit /b 3
)

echo Waiting for Aura to exit...
:wait
tasklist /FI "PID eq %PID%" 2>NUL | find /I "%PID%" >NUL
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >NUL
    goto wait
)

echo Updating Aura files...
robocopy "%SOURCE%" "%TARGET%" /MIR /R:3 /W:5
set "ROBOCOPY_EXIT=%ERRORLEVEL%"
if %ROBOCOPY_EXIT% GEQ 8 (
    echo Update failed with robocopy exit code %ROBOCOPY_EXIT%
    exit /b %ROBOCOPY_EXIT%
)

echo Relaunching Aura...
start "" "%RESTART%"
exit /b 0
