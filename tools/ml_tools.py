"""
Herramientas de Machine Learning para la crew de trading.
"""
from crewai.tools import BaseTool


class TrainXGBoostFilterTool(BaseTool):
    name: str = "train_xgboost_filter"
    description: str = "Entrena o reentrena el filtro XGBoost de señales"

    def _run(self, retrain: bool = True) -> str:
        try:
            from scripts.ml_filter import train_xgboost_filter
            score = train_xgboost_filter(retrain=retrain)
            return f"Modelo XGBoost reentrenado. Score: {score:.3f}"
        except Exception as e:
            return f"Error entrenando XGBoost: {e}"


class EvaluateModelTool(BaseTool):
    name: str = "evaluate_model"
    description: str = "Evalúa el modelo ML actual"

    def _run(self, model_path: str = "models/xgboost_filter.pkl") -> str:
        try:
            from scripts.ml_filter import evaluate_model
            metrics = evaluate_model(model_path)
            return f"Accuracy: {metrics.get('accuracy', 0):.2f} | Precision: {metrics.get('precision', 0):.2f} | Recall: {metrics.get('recall', 0):.2f}"
        except Exception as e:
            return f"Error evaluando modelo: {e}"


class FeatureImportanceTool(BaseTool):
    name: str = "feature_importance"
    description: str = "Muestra la importancia de features del modelo"

    def _run(self, top_n: int = 10) -> str:
        try:
            from scripts.ml_filter import get_feature_importance
            fi = get_feature_importance(top_n=top_n)
            return f"Top {top_n} features:\n" + "\n".join([f"  {k}: {v:.4f}" for k, v in fi.items()])
        except Exception as e:
            return f"Error: {e}"


train_xgboost_filter_tool = TrainXGBoostFilterTool()
evaluate_model_tool = EvaluateModelTool()
feature_importance_tool = FeatureImportanceTool()
