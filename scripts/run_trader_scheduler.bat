@echo off
REM ============================================================
REM  PRO TRADER — Scheduler Automatico para Windows
REM  Ejecuta el pipeline multi-estrategia cada hora en sesion USA
REM ============================================================
title PRO TRADER — MT5 Auto Pilot
cd /d "%~dp0"

set CAPITAL=1024.67
set LOG_FILE=logs\trader_scheduler.log
if not exist "%LOG_FILE%" echo. > "%LOG_FILE%"

echo ============================================ >> "%LOG_FILE%"
echo %date% %time% - INICIANDO PRO TRADER SCHEDULER >> "%LOG_FILE%"
echo ============================================ >> "%LOG_FILE%"

:MENU
cls
echo ============================================================
echo   PRO TRADER — Scheduler Automatico Windows
echo ============================================================
echo.
echo   1. Iniciar scheduler (cada hora, Lun-Vie)
echo   2. Ejecutar un solo ciclo
echo   3. Probar conexion MT5
echo   4. Ver ultimos logs
echo   5. Salir
echo.
set /p opcion="Selecciona (1-5): "

if "%opcion%"=="1" goto START_SCHEDULER
if "%opcion%"=="2" goto SINGLE_CYCLE
if "%opcion%"=="3" goto TEST_MT5
if "%opcion%"=="4" goto VIEW_LOGS
if "%opcion%"=="5" exit /b
goto MENU

:TEST_MT5
cls
echo ============================================================
echo   PRUEBA DE CONEXION MT5
echo ============================================================
python scripts\test_mt5_connection.py
echo.
pause
goto MENU

:SINGLE_CYCLE
cls
echo ============================================================
echo   EJECUTANDO CICLO UNICO
echo ============================================================
python src\pro_trader_crew\main.py
if %errorlevel% equ 0 (
    echo ✅ Ciclo completado
    echo %date% %time% - Ciclo OK >> "%LOG_FILE%"
) else (
    echo ⚠️  Ciclo con errores
    echo %date% %time% - Ciclo ERROR >> "%LOG_FILE%"
)
pause
goto MENU

:VIEW_LOGS
cls
echo ============================================================
echo   ULTIMOS 20 EVENTOS
echo ============================================================
if exist "%LOG_FILE%" (
    powershell -Command "Get-Content '%LOG_FILE%' -Tail 20"
) else (
    echo Sin logs aun
)
pause
goto MENU

:START_SCHEDULER
cls
echo ============================================================
echo   SCHEDULER INICIADO
echo   Horario: Lun-Vie, 9:30-16:00 ET
echo   Ciclo cada 1 hora
echo   CTRL+C para detener
echo ============================================================
echo %date% %time% - SCHEDULER INICIADO >> "%LOG_FILE%"

:SCHEDULER_LOOP
    for /f %%d in ('powershell -Command "(Get-Date).DayOfWeek.Value__"') do set DIA=%%d
    set HORA=%time:~0,2%
    set MIN=%time:~3,2%
    set /a TOTAL_MIN=HORA*60+MIN
    
    if %DIA% geq 1 if %DIA% leq 5 (
        if %TOTAL_MIN% geq 570 if %TOTAL_MIN% leq 960 (
            echo %date% %time% - Ejecutando pipeline... >> "%LOG_FILE%"
            python src\pro_trader_crew\main.py
            if %errorlevel% equ 0 (
                echo ✅ %date% %time% - OK >> "%LOG_FILE%"
            ) else (
                echo ⚠️ %date% %time% - ERROR >> "%LOG_FILE%"
            )
            goto WAIT
        )
    )
    
    cls
    echo ============================================================
    echo   Fuera de horario de mercado
    echo   Proximo ciclo en hora valida (Lun-Vie 9:30-16:00 ET)
    echo   CTRL+C para detener
    echo ============================================================

:WAIT
    echo ⏳ Esperando 1 hora...
    timeout /t 3600 /nobreak >nul
    goto SCHEDULER_LOOP
