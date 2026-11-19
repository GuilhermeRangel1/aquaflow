"""Reproducible hybrid telemetry pipeline for the AquaFlow academic demo."""

import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from airflow.sdk import dag, get_current_context, task

ML_ROOT = Path("/opt/airflow/ml")
DATA_ROOT = Path("/opt/airflow/data/ml")
TRAINING_PYTHON = "/home/airflow/aquaflow-training/bin/python"


@dag(
    dag_id="aquaflow_hybrid_telemetry_pipeline",
    description="Gera, analisa e prepara telemetria híbrida e treina um modelo candidato.",
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    schedule=None,
    catchup=False,
    tags=["aquaflow", "dados-hibridos", "ml"],
)
def hybrid_telemetry_pipeline():
    @task
    def generate_data() -> str:
        run_id = get_current_context()["run_id"]
        run_key = hashlib.sha256(run_id.encode()).hexdigest()
        raw_data = DATA_ROOT / "airflow" / run_key / "raw" / "household_readings.csv"
        subprocess.run(
            [
                sys.executable,
                str(ML_ROOT / "build_real_dataset.py"),
                "--calibration",
                "--output",
                str(raw_data),
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
        )
        return str(raw_data)

    @task
    def analyze_data(input_file: str) -> str:
        analysis_data = Path(input_file).parent.parent / "analysis"
        subprocess.run(
            [
                sys.executable,
                str(ML_ROOT / "prepare_dataset.py"),
                "analyze",
                "--input",
                input_file,
                "--output-dir",
                str(analysis_data),
                "--timezone",
                "America/Sao_Paulo",
            ],
            check=True,
        )
        return str(analysis_data / "eda_report.json")

    @task
    def prepare_data(input_file: str, _report_file: str) -> str:
        prepared_data = Path(input_file).parent.parent / "prepared"
        subprocess.run(
            [
                sys.executable,
                str(ML_ROOT / "prepare_dataset.py"),
                "prepare",
                "--input",
                input_file,
                "--output-dir",
                str(prepared_data),
                "--timezone",
                "America/Sao_Paulo",
            ],
            check=True,
        )
        return str(prepared_data)

    @task
    def train_candidate(prepared_dir: str) -> str:
        prepared = Path(prepared_dir)
        output = prepared.parent / "training"
        run_id = get_current_context()["run_id"]
        subprocess.run(
            [
                TRAINING_PYTHON,
                str(ML_ROOT / "train_model.py"),
                "--features",
                str(prepared / "features.csv"),
                "--labels",
                str(prepared / "labels.csv"),
                "--metadata",
                str(prepared / "metadata.csv"),
                "--output-dir",
                str(output),
                "--bench-calibration",
                str(ML_ROOT / "collection" / "bench-calibration-v1.json"),
                "--timezone",
                "America/Sao_Paulo",
                "--experiment-name",
                "aquaflow-hybrid-airflow",
                "--tracking-uri",
                os.environ["MLFLOW_TRACKING_URI"],
            ],
            check=True,
            env={**os.environ, "AQUAFLOW_AIRFLOW_RUN_ID": run_id},
        )
        return str(output / "metrics.json")

    raw_file = generate_data()
    report_file = analyze_data(raw_file)
    train_candidate(prepare_data(raw_file, report_file))


hybrid_telemetry_pipeline()
