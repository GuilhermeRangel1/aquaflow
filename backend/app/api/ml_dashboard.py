import asyncio
import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime, BaseModel

from app.api.deps import current_user, root_user
from app.db.models import Device, Property, User
from app.export_training_data import export_reviewed
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


class PhysicalTrainingCollection(BaseModel):
    device_id: UUID
    development_start: AwareDatetime
    evaluation_start: AwareDatetime
    evaluation_end: AwareDatetime


async def _export_physical_collection(
    request: Request, collection: PhysicalTrainingCollection, output: Path
) -> None:
    development_start = collection.development_start
    evaluation_start = collection.evaluation_start
    evaluation_end = collection.evaluation_end
    if (
        not development_start
        < evaluation_start
        < evaluation_end
        <= datetime.now(evaluation_end.tzinfo)
    ):
        raise ValueError("Configure períodos cronológicos já concluídos para treino e avaliação.")
    factory = request.app.state.session_factory
    async with factory() as session:
        device = await session.get(Device, collection.device_id)
        if device is None or device.expected_interval_seconds != 30:
            raise ValueError("Configure um medidor físico cadastrado com intervalo de 30 segundos.")
        property_record = await session.get(Property, device.property_id)
        if property_record is None or property_record.archived_at is not None:
            raise ValueError("Configure um medidor de uma propriedade ativa.")
        timezone = property_record.timezone
    for name, start, end in (
        ("development", development_start, evaluation_start),
        ("evaluation", evaluation_start, evaluation_end),
    ):
        count = await export_reviewed(
            factory, collection.device_id, start, end, "physical", output / f"{name}.csv"
        )
        if not count:
            raise ValueError("Treino e avaliação precisam de leituras com rótulos revisados.")
    (output / "timezone.txt").write_text(timezone, encoding="utf-8")


def _retrainer_request(url: str, method: str, collection_id: str | None = None) -> dict[str, Any]:
    data = collection_id.encode("ascii") if collection_id else None
    request = urllib.request.Request(f"{url.rstrip('/')}/jobs", data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read())
            return payload if isinstance(payload, dict) else {}
    except urllib.error.HTTPError as error:
        if error.code == 409:
            payload = json.loads(error.read())
            return payload if isinstance(payload, dict) else {}
        raise


@router.post("/training-jobs", status_code=202)
async def start_training_job(request: Request, _user: User = Depends(root_user)) -> dict[str, Any]:
    settings = request.app.state.settings
    url = settings.ml_retraining_url
    if not url:
        raise HTTPException(status_code=503, detail={"code": "ml_retraining_unavailable"})
    collection_id = None
    try:
        if settings.ml_physical_training_collection:
            collection = PhysicalTrainingCollection.model_validate_json(
                settings.ml_physical_training_collection
            )
            collection_id = str(uuid4())
            await _export_physical_collection(
                request, collection, settings.ml_training_exports_dir / collection_id
            )
        return await asyncio.to_thread(_retrainer_request, url, "POST", collection_id)
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ml_physical_training_collection_invalid",
                "message": str(error)
                if collection_id
                else ("A configuração da coleta física para treinamento é inválida."),
            },
        ) from None
    except (OSError, TimeoutError, urllib.error.URLError):
        raise HTTPException(status_code=503, detail={"code": "ml_retraining_unavailable"}) from None


@router.get("/training-jobs/{job_id}")
async def get_training_job(
    job_id: str, request: Request, _user: User = Depends(root_user)
) -> dict[str, Any]:
    url = request.app.state.settings.ml_retraining_url
    if not url:
        raise HTTPException(status_code=503, detail={"code": "ml_retraining_unavailable"})
    try:
        result = await asyncio.to_thread(_retrainer_request, url, "GET")
    except (OSError, TimeoutError, urllib.error.URLError):
        raise HTTPException(status_code=503, detail={"code": "ml_retraining_unavailable"}) from None
    if result.get("id") != job_id:
        raise HTTPException(status_code=404, detail={"code": "ml_training_job_not_found"})
    return result


@router.get("/training-dashboard", response_model=MLTrainingDashboardOutput)
async def get_training_dashboard(
    request: Request,
    execution_id: str | None = Query(default=None, min_length=1, max_length=160),
    user: User = Depends(current_user),
) -> MLTrainingDashboardOutput:
    settings = request.app.state.settings
    is_admin = str(user.email).lower() == str(settings.root_user_email).lower()
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
    if not is_admin:
        # Reviewed collection manifests can identify the contributing devices and readings.
        private_fields = {"development", "evaluation"}
        active_report = {
            key: value for key, value in active_report.items() if key not in private_fields
        }
        report = {key: value for key, value in report.items() if key not in private_fields}
    return MLTrainingDashboardOutput(
        active_model=active_model_summary(active_report, model_hash),
        active_execution_id=active_execution["id"] if active_execution else None,
        selected_execution_id=selected_execution["id"] if selected_execution else None,
        history_available=bool(executions),
        worker_status=worker,
        executions=[
            {key: value for key, value in item.items() if key != "run_id"} for item in executions
        ],
        active_report=active_report,
        report=report,
    )
