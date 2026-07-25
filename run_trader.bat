@echo off
REM =============================================
REM  PRO TRADER CREW — Inicio rapido en Windows
REM  Cuenta Demo Exness MT5
REM =============================================

echo.
echo ============================================
echo   PRO TRADER — Trading con MT5 Demo
echo ============================================
echo.

REM 1. Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado. Instalalo desde python.org
    pause
    exit /b 1
)
echo [OK] Python encontrado

REM 2. Instalar dependencias
echo.
echo Instalando dependencias...
pip install MetaTrader5 python-dotenv ccxt pandas numpy crewai crewai-tools

REM 3. Probar conexion MT5
echo.
echo Probando conexion a MT5 Demo Exness...
python scripts\test_mt5_connection.py

REM 4. Preguntar modo
echo.
echo ============================================
echo   SELECCIONA MODO:
echo   1. Un ciclo de analisis
echo   2. Modo vigilante (cada hora)
echo   3. Probar conexion MT5 nuevamente
echo ============================================
set /p mode="Opcion (1-3): "

if "%mode%"=="1" (
    python src/pro_trader_crew/main.py
) else if "%mode%"=="2" (
    python src/pro_trader_crew/main.py --watch
) else if "%mode%"=="3" (
    python scripts/test_mt5_connection.py
) else (
    echo Opcion no valida
)

pause
