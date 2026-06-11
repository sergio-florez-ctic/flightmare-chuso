@echo off
setlocal EnableExtensions

set "IMAGE_NAME=flightmare"
set "DOCKERFILE_DIR=%~dp0"

if /I "%~1"=="run" goto :run
if /I "%~1"=="build" goto :build_only
if /I "%~1"=="help" goto :help
if /I "%~1"=="-h" goto :help
if /I "%~1"=="--help" goto :help
if not "%~1"=="" (
    echo Opcion desconocida: %~1
    goto :help
)

goto :rebuild

:rebuild
echo ==^> Deteniendo contenedores de %IMAGE_NAME%...
for /f "tokens=*" %%i in ('docker ps -q --filter "ancestor=%IMAGE_NAME%" 2^>nul') do (
    docker stop %%i >nul 2>&1
)

echo ==^> Eliminando imagen %IMAGE_NAME%...
docker rmi -f %IMAGE_NAME% >nul 2>&1

echo ==^> Build desde cero (sin cache)...
docker build --no-cache -t %IMAGE_NAME% "%DOCKERFILE_DIR%"
if errorlevel 1 goto :fail

goto :smoke_test

:build_only
echo ==^> Build con cache...
docker build -t %IMAGE_NAME% "%DOCKERFILE_DIR%"
if errorlevel 1 goto :fail
goto :smoke_test

:smoke_test
echo ==^> Smoke test...
docker run --rm %IMAGE_NAME% python3 -c "import flightgym; from rpg_baselines.common.policies import MlpPolicy; print('flightgym + rpg_baselines OK')"
if errorlevel 1 goto :fail

docker run --rm %IMAGE_NAME% python3 -c "import ruamel.yaml; print('ruamel.yaml', ruamel.yaml.version_info)"
if errorlevel 1 goto :fail

echo.
echo Listo. Entra al contenedor con:
echo   launch.bat run
echo   o: docker run -it --rm %IMAGE_NAME% bash
echo.
echo Prueba RL (headless, sin graficos):
echo   cd /home/flightmare/flightrl/examples
echo   export MPLBACKEND=Agg
echo   python3 run_drone_control.py --train 0 --render 0
goto :end

:run
docker image inspect %IMAGE_NAME% >nul 2>&1
if errorlevel 1 (
    echo La imagen %IMAGE_NAME% no existe. Ejecuta: launch.bat
    exit /b 1
)
docker run -it --rm %IMAGE_NAME% bash
goto :end

:help
echo Uso: launch.bat [comando]
echo.
echo   launch.bat         Rebuild completo sin cache + smoke test
echo   launch.bat build   Build con cache + smoke test
echo   launch.bat run     Abrir shell interactivo en el contenedor
echo   launch.bat help    Mostrar esta ayuda
goto :end

:fail
echo.
echo ERROR: fallo el build o el smoke test.
exit /b 1

:end
endlocal
