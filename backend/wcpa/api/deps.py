"""依赖注入。"""
import json
from wcpa.shared.paths import PREDICTIONS_DIR
from wcpa.schemas.artifact import TournamentPrediction


def load_prediction_artifact_unchecked() -> TournamentPrediction | None:
    """从 outputs/predictions/ 读取已存的预测 artifact。"""
    artifact_path = PREDICTIONS_DIR / "tournament-prediction.json"
    if not artifact_path.exists():
        return None
    with open(artifact_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return TournamentPrediction(**data)


def get_prediction_artifact(strict: bool = True) -> TournamentPrediction | None:
    """Return prediction artifact only if it is valid for production by default."""
    artifact = load_prediction_artifact_unchecked()
    if artifact is None:
        return None
    if strict:
        report = artifact.data_quality_report
        if not artifact.data_verified or report is None or report.status != "ready":
            return None
    return artifact
