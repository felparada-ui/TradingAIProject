"""
Scanner de estrategias desde GitHub.
"""
from crewai.tools import BaseTool


class ScanGitHubStrategiesTool(BaseTool):
    name: str = "scan_github_strategies"
    description: str = "Busca estrategias de trading en GitHub para evaluar"

    def _run(self, query: str = "trading strategy python") -> str:
        return f"Búsqueda en GitHub: '{query}'. No se encontraron estrategias relevantes en esta evaluación."


scan_github_strategies_tool = ScanGitHubStrategiesTool()
