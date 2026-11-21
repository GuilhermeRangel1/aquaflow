"""Internal HTTP worker for isolated model retraining and activation."""

import hashlib
import json
import os
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(os.getenv("ML_DATA_ROOT", "data/ml"))
ACTIVE = ROOT / "training-bench-v2"
JOBS: dict[str, Any] = {"id": None, "status": "idle", "message": ""}
LOCK = threading.Lock()


def _train(job_id: str) -> None:
    candidate = ACTIVE / "candidates" / job_id
    run_data = ACTIVE / "work" / job_id
    raw_dir = run_data / "raw"
    analysis_dir = run_data / "analysis"
    prepared_dir = run_data / "prepared"
    raw_file = raw_dir / "household_readings.csv"
    JOBS.update(status="running", message="Treinando e avaliando modelos")
    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                sys.executable,
                "build_real_dataset.py",
                "--bench-dir",
                "data/dados_reais",
                "--bench-calibration",
                "collection/bench-calibration-v1.json",
                "--output",
                str(raw_file),
                "--seed",
                "42",
                "--start",
                "2026-09-01T00:00:00-03:00",
                "--timezone",
                "America/Sao_Paulo",
                "--days",
                "16",
                "--interval-minutes",
                "5",
            ],
            check=True,
            env=os.environ.copy(),
        )
        subprocess.run(
            [
                sys.executable,
                "prepare_dataset.py",
                "analyze",
                "--input",
                str(raw_file),
                "--output-dir",
                str(analysis_dir),
                "--timezone",
                "America/Sao_Paulo",
            ],
            check=True,
            env=os.environ.copy(),
        )
        subprocess.run(
            [
                sys.executable,
                "prepare_dataset.py",
                "prepare",
                "--input",
                str(raw_file),
                "--output-dir",
                str(prepared_dir),
                "--timezone",
                "America/Sao_Paulo",
            ],
            check=True,
            env=os.environ.copy(),
        )
        subprocess.run(
            [
                sys.executable,
                "train_model.py",
                "--features",
                str(prepared_dir / "features.csv"),
                "--labels",
                str(prepared_dir / "labels.csv"),
                "--metadata",
                str(prepared_dir / "metadata.csv"),
                "--output-dir",
                str(candidate),
                "--bench-calibration",
                "collection/bench-calibration-v1.json",
                "--timezone",
                "America/Sao_Paulo",
            ],
            check=True,
            env=os.environ.copy(),
        )
        report = json.loads((candidate / "metrics.json").read_text(encoding="utf-8"))
        model_hash = hashlib.sha256(
            (candidate / "best_model.joblib").read_bytes()
        ).hexdigest()
        if report.get("model_sha256") != model_hash:
            raise ValueError("O hash do modelo não confere com o relatório")
        selected = report.get("selected_model")
        metrics = report.get("candidates", {}).get(selected, {}).get("validation", {})
        stress = report.get("stress_test_evaluation", {}).get("selected_model", {})
        ap = metrics.get("average_precision")
        if not isinstance(ap, (int, float)) or not 0 <= ap <= 1:
            raise ValueError("A validação temporal do modelo selecionado é inválida")
        if stress and not 0 <= stress.get("average_precision", -1) <= 1:
            raise ValueError("A avaliação de estresse do modelo selecionado é inválida")
        active_pointer = ACTIVE / "active-model.json"
        if active_pointer.is_file():
            active_directory = Path(json.loads(active_pointer.read_text(encoding="utf-8"))["directory"])
            if active_directory.is_absolute() or ".." in active_directory.parts:
                raise ValueError("A referência do modelo ativo é inválida")
            active_report = json.loads((ACTIVE / active_directory / "metrics.json").read_text(encoding="utf-8"))
            active_model = active_report["selected_model"]
            active_test = active_report["test_evaluation"][active_model]
            candidate_test = report["test_evaluation"][selected]
            active_stress = active_report["stress_test_evaluation"]["selected_model"]
            candidate_stress = report["stress_test_evaluation"]["selected_model"]
            for label, before, after in (("teste", active_test, candidate_test), ("estresse", active_stress, candidate_stress)):
                if after["average_precision"] < before["average_precision"] or after["recall"] < before["recall"]:
                    raise ValueError(f"Modelo candidato reprovado: AP ou recall caiu no conjunto de {label}")
        pointer = ACTIVE / "active-model.json"
        temporary = ACTIVE / f".active-{job_id}.tmp"
        temporary.write_text(
            json.dumps({"directory": f"candidates/{job_id}"}), encoding="utf-8"
        )
        os.replace(temporary, pointer)
        JOBS.update(
            status="succeeded",
            message=f"{selected} validado e ativado",
            model_hash=model_hash,
        )
    except Exception as error:  # noqa: BLE001
        JOBS.update(status="failed", message=str(error)[:500])
    finally:
        LOCK.release()


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path not in ("/health", "/jobs"):
            self._json(404, {"detail": "not found"})
            return
        self._json(200, JOBS.copy())

    def do_POST(self) -> None:
        if self.path != "/jobs":
            self._json(404, {"detail": "not found"})
            return
        if not LOCK.acquire(blocking=False):
            self._json(409, JOBS.copy())
            return
        job_id = str(uuid.uuid4())
        JOBS.clear()
        JOBS.update(id=job_id, status="queued", message="Treinamento na fila")
        threading.Thread(target=_train, args=(job_id,), daemon=True).start()
        self._json(202, JOBS.copy())

    def log_message(self, _format: str, *_args: Any) -> None:
        return


if __name__ == "__main__":
    ACTIVE.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(
        ("0.0.0.0", int(os.getenv("ML_RETRAIN_PORT", "8082"))), Handler
    ).serve_forever()
