import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import current_user
from app.db.models import User
from app.schemas.ml_dashboard import MLTrainingDashboardOutput
from app.services.ml_dashboard import (
    TrainingDashboardUnavailable,
    active_model_summary,
    list_mlflow_executions,
    load_active_training_report,
    load_mlflow_execution_report,
    ml_worker_status,
)

router = APIRouter(prefix="/api/v1/ml", tags=["experimental ML dashboard"])


@router.get("/training-dashboard", response_model=MLTrainingDashboardOutput)
async def get_training_dashboard(
    request: Request,
    execution_id: str | None = Query(default=None, min_length=1, max_length=160),
    user: User = Depends(current_user),
) -> MLTrainingDashboardOutput:
    del user
    try:
        report, model_hash = load_active_training_report(
            request.app.state.settings.ml_artifacts_dir
        )
    except TrainingDashboardUnavailable:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ml_dashboard_unavailable",
                "message": "Os dados da execução ativa do modelo estão indisponíveis.",
            },
        ) from None
    active_report = report
    settings = request.app.state.settings
    experiment_id = active_report.get("mlflow_experiment_id")
    experiment_id = experiment_id if isinstance(experiment_id, str) else None
    executions, worker = await asyncio.gather(
        list_mlflow_executions(settings.mlflow_tracking_uri, experiment_id),
        ml_worker_status(settings.ml_worker_health_url),
    )
    active_execution = next(
        (item for item in executions if item.get("model_version") == model_hash), None
    )
    selected_execution = active_execution
    if execution_id:
        selected_execution = next((item for item in executions if item["id"] == execution_id), None)
        if selected_execution is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "ml_execution_not_found",
                    "message": "Esta execução de treinamento não está disponível.",
                },
            )
        if selected_execution.get("model_version") != model_hash:
            try:
                report = await load_mlflow_execution_report(
                    settings.ml_artifacts_dir,
                    selected_execution["run_id"],
                )
            except TrainingDashboardUnavailable:
                raise HTTPException(
                    status_code=503,
                    detail={"code": "ml_execution_report_unavailable"},
                ) from None
    return MLTrainingDashboardOutput(
        active_model=active_model_summary(active_report, model_hash),
        active_execution_id=active_execution["id"] if active_execution else None,
        selected_execution_id=selected_execution["id"] if selected_execution else None,
        history_available=bool(executions),
        worker_status=worker,
        executions=[
            {key: value for key, value in item.items() if key != "run_id"}
            for item in executions
        ],
        active_report=active_report,
        report=report,
    )
