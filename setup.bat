@echo off
echo Creando estructura del proyecto TradingAIProject...
echo.

REM Crear carpetas
if not exist .devcontainer mkdir .devcontainer
if not exist src\trading_bot_crew\config mkdir src\trading_bot_crew\config
if not exist src\trading_bot_crew\tools mkdir src\trading_bot_crew\tools
if not exist data\historical mkdir data\historical
if not exist data\backtest_results mkdir data\backtest_results
if not exist data\models mkdir data\models
if not exist notebooks mkdir notebooks

REM Crear devcontainer.json
(
echo {
echo     "name": "CrewAI Trading Bot",
echo     "image": "python:3.11-slim",
echo     "customizations": {
echo         "vscode": {
echo             "extensions": [
echo                 "ms-python.python",
echo                 "ms-python.vscode-pylance",
echo                 "ms-toolsai.jupyter"
echo             ]
echo         }
echo     },
echo     "postCreateCommand": "pip install --upgrade pip && pip install crewai crewai-tools pandas numpy ta matplotlib seaborn scikit-learn openai python-dotenv pyyaml"
echo }
) > .devcontainer\devcontainer.json

REM Crear agents.yaml
(
echo market_analyst:
echo   role: Data Analyst
echo   goal: "Analizar datos historicos de trading para identificar patrones estadisticos significativos"
echo   backstory: "Eres un especialista en analisis de series temporales financieras con experiencia en modelos probabilisticos"
echo   verbose: true
echo   allow_delegation: false
echo.
echo risk_manager:
echo   role: Risk Management Expert
echo   goal: "Calcular metricas de riesgo y posicion optima para cada operacion"
echo   backstory: "Eres un experto en gestion de riesgos cuantitativos con dominio de VaR, drawdown y Kelly Criterion"
echo   verbose: true
echo   allow_delegation: false
echo.
echo strategy_developer:
echo   role: Trading Strategy Developer
echo   goal: "Formular estrategias de trading con relacion riesgo-recompensa favorable"
echo   backstory: "Eres un Quant con experiencia en desarrollo de estrategias algoritmicas y backtesting"
echo   verbose: true
echo   allow_delegation: true
echo.
echo backtest_validator:
echo   role: Backtest Validator
echo   goal: "Validar estrategias con backtesting riguroso antes de considerar operacion real"
echo   backstory: "Eres un especialista en validacion de modelos financieros y analisis de sensibilidad"
echo   verbose: true
echo   allow_delegation: false
) > src\trading_bot_crew\config\agents.yaml

REM Crear main.py
(
echo import os
echo from dotenv import load_dotenv
echo from crewai import Crew, Process
echo from crewai import Agent, Task
echo import yaml
echo.
echo load_dotenv()
echo.
echo def load_agents_from_yaml():
echo     config_path = 'src/trading_bot_crew/config/agents.yaml'
echo     with open(config_path, 'r', encoding='utf-8') as file:
echo         config = yaml.safe_load(file)
echo     agents = {}
echo     for name, cfg in config.items():
echo         agents[name] = Agent(
echo             role=cfg['role'],
echo             goal=cfg['goal'],
echo             backstory=cfg['backstory'],
echo             verbose=cfg.get('verbose', True),
echo             allow_delegation=cfg.get('allow_delegation', False)
echo         )
echo     return agents
echo.
echo def main():
echo     print("🚀 Iniciando Trading Bot Crew...")
echo     print("=" * 50)
echo     agents = load_agents_from_yaml()
echo     print("✅ Agentes cargados:")
echo     for name, agent in agents.items():
echo         print(f"  📊 {name}: {agent.role}")
echo     crew = Crew(
echo         agents=list(agents.values()),
echo         tasks=[],
echo         process=Process.hierarchical,
echo         verbose=True
echo     )
echo     print("\n" + "=" * 50)
echo     print("✅ Crew configurado correctamente")
echo     print(f"📊 Agentes disponibles: {', '.join(agents.keys())}")
echo     print("\n💡 Siguiente paso: Definir las tareas en tasks.py")
echo.
echo if __name__ == "__main__":
echo     main()
) > src\trading_bot_crew\main.py

REM Crear pyproject.toml
(
echo [project]
echo name = "trading-bot-crew"
echo version = "0.1.0"
echo description = "Trading bot with CrewAI agents for MT5 data analysis"
echo requires-python = ">=3.11"
echo dependencies = [
echo     "crewai>=0.30.0",
echo     "crewai-tools>=0.1.0",
echo     "pandas>=2.0.0",
echo     "numpy>=1.24.0",
echo     "ta>=0.9.0",
echo     "matplotlib>=3.7.0",
echo     "seaborn>=0.12.0",
echo     "scikit-learn>=1.3.0",
echo     "openai>=1.0.0",
echo     "python-dotenv>=1.0.0",
echo     "pyyaml>=6.0"
echo ]
) > pyproject.toml

REM Crear .env
(
echo OPENAI_API_KEY=sk-tu_clave_openai_aqui
echo.
echo # Si usas SiliconFlow o DeepSeek, descomenta y configura:
echo # OPENAI_API_BASE=https://api.siliconflow.cn/v1
) > .env

REM Crear README.md
(
echo # TradingAIProject
echo.
echo ## Descripcion
echo Sistema de trading con CrewAI para analisis de datos historicos de MT5.
echo.
echo ## Estructura
echo - `src/trading_bot_crew/` - Codigo principal
echo - `data/` - Datos historicos y resultados
echo - `notebooks/` - Analisis exploratorio
echo.
echo ## Como usar
echo 1. Abrir en VS Code con Dev Container
echo 2. Configurar API key en `.env`
echo 3. Ejecutar: `python src/trading_bot_crew/main.py`
) > README.md

echo.
echo ========================================
echo ✅ ESTRUCTURA CREADA EXITOSAMENTE
echo ========================================
echo.
echo 📂 Carpetas creadas:
echo   - .devcontainer/
echo   - src/trading_bot_crew/config/
echo   - src/trading_bot_crew/tools/
echo   - data/historical/
echo   - data/backtest_results/
echo   - data/models/
echo   - notebooks/
echo.
echo 📄 Archivos creados:
echo   - .devcontainer/devcontainer.json
echo   - src/trading_bot_crew/config/agents.yaml
echo   - src/trading_bot_crew/main.py
echo   - pyproject.toml
echo   - .env
echo   - README.md
echo.
echo 🚀 Ahora ejecuta: code .
echo.
pause