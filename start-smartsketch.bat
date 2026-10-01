@echo off
REM ============================================================================
REM  SmartSketch one-click launcher (Windows)
REM
REM  Double-click this file to start the local stack:
REM    Docker Desktop if needed, Neo4j, API, worker and the web UI.
REM
REM  Companion file: start-dev.ps1 in the same folder.
REM
REM  Batch-file safety rules used here on purpose. A violation makes cmd print
REM  something like ". was unexpected at this time." and the window vanishes:
REM    - delayed expansion stays OFF, so "!" never needs escaping
REM    - no "echo" line contains an unescaped "&" "|" "<" ">" or parentheses
REM    - control flow uses labels and goto, never parenthesised blocks
REM    - "echo." for blank lines, never a bare "echo"
REM    - delays use "ping" because "timeout" needs a console handle
REM  ASCII-only, because cmd renders text with the console code page.
REM  Chinese notes live in WINDOWS.md.
REM ============================================================================

setlocal EnableExtensions
title SmartSketch launcher

set "SCRIPT=%~dp0start-dev.ps1"
set "REPO=%~dp0"
set "DOCKER=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe"
set "DOCKER_DESKTOP=%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
set "URL=http://127.0.0.1:5173"
set "NODOCKER=0"

echo.
echo ============================================================
echo   SmartSketch  --  local launcher
echo ============================================================
echo.

if not exist "%SCRIPT%" goto :noscript

REM ------------------------------------------------ 0. is the stack already up?
REM Skip startup only when BOTH the API and the web UI answer. The API alone is
REM not enough: if the frontend is down, opening the browser shows
REM ERR_CONNECTION_REFUSED.
powershell.exe -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3 -UseBasicParsing > $null; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 goto :fresh

powershell.exe -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -TimeoutSec 3 -UseBasicParsing > $null; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 goto :api_only

goto :already_up

:fresh
goto :docker_step

:api_only
echo [1/4] The API is up on 8000 but the web UI on 5173 is not.
echo       Finishing the startup. Docker and Neo4j are left untouched.
echo.
set "NODOCKER=1"
goto :do_start

REM ------------------------------------------------ 1. Docker Desktop / engine
:docker_step
if exist "%DOCKER%" goto :probe_path
docker info >nul 2>&1
goto :probe_done

:probe_path
"%DOCKER%" info >nul 2>&1

:probe_done
if not errorlevel 1 goto :engine_up

tasklist /FI "IMAGENAME eq Docker Desktop.exe" 2>nul | find /I "Docker Desktop.exe" >nul
if not errorlevel 1 goto :docker_running

if not exist "%DOCKER_DESKTOP%" goto :no_docker

echo [1/4] Starting Docker Desktop ...
start "" "%DOCKER_DESKTOP%"
goto :wait_engine

:docker_running
echo [1/4] Docker Desktop is already running. Waiting for its engine.
goto :wait_engine

:engine_up
echo [1/4] The Docker engine is already answering. Not launching Docker Desktop.
goto :neo4j_step

REM ------------------------------------------------ 2. wait for the engine
:wait_engine
echo [2/4] Waiting for the Docker engine. A cold start takes 1-2 minutes.
set /a TRIES=0

:wait_loop
set /a TRIES+=1
if %TRIES% GTR 48 goto :engine_timeout

if exist "%DOCKER%" goto :wait_probe_path
docker info >nul 2>&1
goto :wait_probe_done

:wait_probe_path
"%DOCKER%" info >nul 2>&1

:wait_probe_done
if not errorlevel 1 goto :engine_ready
<nul set /p "=."
ping -n 6 127.0.0.1 >nul
goto :wait_loop

:engine_timeout
echo.
echo [2/4] [WARN] The Docker engine did not answer within 4 minutes.
echo         Continuing anyway. Check the Docker Desktop status window.
echo         If it reports WSL problems, run:  wsl --update
echo.
goto :skip_neo4j

:engine_ready
echo.
echo [2/4] Docker engine is ready.
echo.

REM ------------------------------------------------ 3. Neo4j container
:neo4j_step
echo [3/4] Starting the Neo4j container ...
pushd "%REPO%"
if exist "%DOCKER%" goto :compose_path
docker compose up -d neo4j
goto :compose_done

:compose_path
"%DOCKER%" compose up -d neo4j

:compose_done
if errorlevel 1 goto :compose_failed
echo [3/4] Neo4j container is up. Its health check keeps running.
echo.
goto :compose_end

:compose_failed
echo [3/4] [WARN] docker compose up -d neo4j failed.
echo         Check that .env defines NEO4J_PASSWORD and that Docker Desktop
echo         uses the WSL 2 backend, see Settings - General.
echo.

:compose_end
popd

:skip_neo4j

REM ------------------------------------------------ 4. the stack
:do_start
echo [4/4] Starting API, worker and web UI in separate windows ...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
if errorlevel 1 goto :start_failed

echo Waiting for the web UI to answer ...
set /a WTRIES=0

:wait_web
set /a WTRIES+=1
if %WTRIES% GTR 30 goto :web_not_ready
powershell.exe -NoProfile -Command "try { Invoke-WebRequest -Uri '%URL%' -TimeoutSec 3 -UseBasicParsing > $null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto :web_ready
ping -n 3 127.0.0.1 >nul
goto :wait_web

:web_not_ready
echo.
echo [WARN] The web UI did not answer on %URL%
echo        Check the window titled "SmartSketch web" for the error.
echo.
goto :finish

:web_ready
echo.
echo ============================================================
echo   Ready:   %URL%
echo.
echo   Teacher: demo_teacher  / smartsketch-demo
echo   Student: demo_student  / smartsketch-demo
echo ============================================================
echo.
start "" "%URL%"

:finish
echo.
echo Service windows were opened: API, worker and web.
echo Close those windows to stop the services.
echo.
echo To stop Neo4j, run this in a terminal:
echo     cd /d %REPO%
echo     docker compose stop neo4j
echo.
echo This launcher window can be closed now.
echo.
pause
exit /b 0

REM ------------------------------------------------ all up already
:already_up
echo [1/4] Both services already answer:
echo         API  http://127.0.0.1:8000
echo         Web  %URL%
echo.
echo       Nothing to start. Opening the web UI.
echo       To restart everything, close the API / worker / web windows first.
echo.
start "" "%URL%"
echo.
pause
exit /b 0

REM ------------------------------------------------ no Docker Desktop
:no_docker
echo [1/4] [WARN] Docker Desktop was not found at:
echo         %DOCKER_DESKTOP%
echo.
echo         Install it once by double-clicking install-docker-desktop.bat
echo         in this folder.
echo.
echo         Continuing without Neo4j. Login, courses and reviews still work,
echo         but the graph, publish and chat features return 503.
echo.
goto :skip_neo4j

REM ------------------------------------------------ error paths
:start_failed
echo.
echo [ERROR] start-dev.ps1 failed. Read the output above.
echo.
pause
exit /b 1

:noscript
echo [ERROR] Missing companion file:
echo         %SCRIPT%
echo         Keep start-dev.ps1 in the same folder as this launcher.
echo.
pause
exit /b 1
