@echo off
REM Rastrea el tema ambiental en los 86 municipios. Doble click y listo.
REM
REM Al terminar deja los datos en data\processed\temas\temas_86.sqlite y
REM muestra el resumen por pantalla.
cd /d "%~dp0"

REM DeepSeek y no Gemini: el motor hace una llamada por municipio, o sea 86 por
REM corrida, y Gemini tiene techo de 200 diarias. Con DeepSeek se puede volver a
REM correr mientras se afinan las senales.
if "%MIP_LLM_PROVIDER%"=="" set MIP_LLM_PROVIDER=deepseek

echo.
echo ===============================================================
echo   Tema ambiental - los 86 municipios
echo   Proveedor: %MIP_LLM_PROVIDER%
echo ===============================================================
echo.
echo Antes de largar los 86 conviene mirar uno. Elegi:
echo.
echo   [1] Un municipio de prueba (Chascomus) - 1 minuto
echo   [2] Los 86                             - puede tardar
echo   [3] Ver lo ya rastreado, sin volver a correr
echo.
set /p OPCION="Opcion [1]: "
if "%OPCION%"=="" set OPCION=1

if "%OPCION%"=="2" goto todos
if "%OPCION%"=="3" goto ver

python -u src\temas\motor_temas.py --tema ambiental --municipio Chascomus
echo.
echo ---------------------------------------------------------------
echo Mira las citas de arriba antes de seguir. Cada [si] tiene que
echo estar sostenido por su cita: si la cita habla de un tramite ante
echo el OPDS, eso NO es fiscalizacion municipal.
echo.
echo Si las citas tienen sentido, volve a correr y elegi la opcion 2.
goto fin

:todos
python -u src\temas\motor_temas.py --tema ambiental --all
goto fin

:ver
python -u src\temas\motor_temas.py --tema ambiental --cobertura
echo.
echo Para el detalle de un municipio:
echo    python src\temas\motor_temas.py --tema ambiental --ficha Chascomus

:fin
echo.
pause
