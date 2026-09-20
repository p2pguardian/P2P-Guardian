@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where dotnet >nul 2>&1
if errorlevel 1 (
  echo .NET 8 SDK is required to build the native controller.
  echo.
  echo Install the Windows x64 .NET 8 SDK, then run this file again.
  pause
  exit /b 1
)

set "SOURCE=%~dp0"
rem native_controller is inside src, so the repository root is TWO levels up.
set "ROOT=%~dp0..\..\"
set "PAYLOAD_PUBLISH=%ROOT%payload\native_controller_publish"
set "STAGE_ROOT=%TEMP%\P2PG_ControllerBuild"
set "STAGE_PROJECT=%STAGE_ROOT%\P2P_Guardian_Control.csproj"
set "STAGE_PUBLISH=%STAGE_ROOT%\publish"

rem Build from a deliberately short source path. The extracted installer project can
rem live under a very deep Desktop/Downloads path, which can break SDK-generated
rem .deps.json/runtimeconfig.json files even when compilation succeeds.
dotnet build-server shutdown >nul 2>&1
if exist "%STAGE_ROOT%" rmdir /s /q "%STAGE_ROOT%"
if exist "%PAYLOAD_PUBLISH%" rmdir /s /q "%PAYLOAD_PUBLISH%"

mkdir "%STAGE_ROOT%"
if errorlevel 1 goto :fail
mkdir "%STAGE_PUBLISH%"
if errorlevel 1 goto :fail

rem Stage only the controller source/project assets; never stage user token/config files.
xcopy /e /i /y "%SOURCE%*.cs" "%STAGE_ROOT%\" >nul
xcopy /e /i /y "%SOURCE%*.csproj" "%STAGE_ROOT%\" >nul
xcopy /e /i /y "%SOURCE%*.ico" "%STAGE_ROOT%\" >nul

if not exist "%STAGE_PROJECT%" goto :fail

echo Building self-contained P2P Guardian Control...
echo.

dotnet restore "%STAGE_PROJECT%" -r win-x64
if errorlevel 1 goto :fail

echo.
echo Publishing complete folder-based self-contained controller...
dotnet publish "%STAGE_PROJECT%" -c Release -r win-x64 --self-contained true /p:UseAppHost=true /p:GenerateRuntimeConfigurationFiles=true /p:GenerateDependencyFile=true --no-restore -o "%STAGE_PUBLISH%"
if errorlevel 1 goto :fail

if not exist "%STAGE_PUBLISH%\P2P_Guardian_Control.exe" goto :missingexe
if not exist "%STAGE_PUBLISH%\P2P_Guardian_Control.dll" goto :missingdll
if not exist "%STAGE_PUBLISH%\P2P_Guardian_Control.deps.json" goto :missingdeps
if not exist "%STAGE_PUBLISH%\P2P_Guardian_Control.runtimeconfig.json" goto :missingruntime

for /f %%N in ('dir /b "%STAGE_PUBLISH%\*.dll" ^| find /c /v ""') do set "DLLCOUNT=%%N"
if not defined DLLCOUNT set "DLLCOUNT=0"
if "%DLLCOUNT%"=="0" goto :missingdlls

mkdir "%PAYLOAD_PUBLISH%"
rem Use ROBOCOPY for the large self-contained publish folder.
robocopy "%STAGE_PUBLISH%" "%PAYLOAD_PUBLISH%" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :copyfail

rem Remove development-only files from the public installer payload.
del /s /q "%PAYLOAD_PUBLISH%\*.pdb" >nul 2>&1
del /s /q "%PAYLOAD_PUBLISH%\*.xml" >nul 2>&1

if not exist "%PAYLOAD_PUBLISH%\P2P_Guardian_Control.exe" goto :copyfail
if not exist "%PAYLOAD_PUBLISH%\P2P_Guardian_Control.dll" goto :copyfail
if not exist "%PAYLOAD_PUBLISH%\P2P_Guardian_Control.deps.json" goto :copyfail
if not exist "%PAYLOAD_PUBLISH%\P2P_Guardian_Control.runtimeconfig.json" goto :copyfail

rmdir /s /q "%STAGE_ROOT%" >nul 2>&1

echo.
echo Native controller build complete.
echo Complete publish output copied to:
echo %PAYLOAD_PUBLISH%
echo.
pause
exit /b 0

:missingexe
echo.
echo BUILD FAILED: publish did not create P2P_Guardian_Control.exe.
goto :fail

:missingdll
echo.
echo BUILD FAILED: publish did not create P2P_Guardian_Control.dll.
goto :fail

:missingdeps
echo.
echo BUILD FAILED: publish did not create P2P_Guardian_Control.deps.json.
goto :fail

:missingruntime
echo.
echo BUILD FAILED: publish did not create P2P_Guardian_Control.runtimeconfig.json.
goto :fail

:missingdlls
echo.
echo BUILD FAILED: no runtime DLLs were created; expected a folder-based self-contained publish.
goto :fail

:copyfail
echo.
echo BUILD FAILED: could not copy the verified publish output into the installer payload.
goto :fail

:fail
echo.
echo BUILD FAILED.
if exist "%STAGE_ROOT%" rmdir /s /q "%STAGE_ROOT%" >nul 2>&1
pause
exit /b 1
