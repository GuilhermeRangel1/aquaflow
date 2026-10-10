"""Reproducible mock telemetry pipeline for the AquaFlow academic demo."""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from airflow.sdk import dag, task

ML_ROOT = Path("/opt/airflow/ml")
DATA_ROOT = Path("/opt/airflow/data/ml")
RAW_DATA = DATA_ROOT / "raw" / "mock_readings.csv"
ANALYSIS_DATA = DATA_ROOT / "analysis"
PREPARED_DATA = DATA_ROOT / "prepared"


@dag(
    dag_id="aquaflow_mock_telemetry_pipeline",
    description="Gera, analisa e prepara telemetria sintética do AquaFlow.",
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    schedule=None,
    catchup=False,
    tags=["aquaflow", "dados-mockados", "ml"],
)
def mock_telemetry_pipeline():
    @task
    def generate_data() -> str:
        subprocess.run(
            [
                sys.executable,
                str(ML_ROOT / "generate_mock_data.py"),
                "--output",
                str(RAW_DATA),
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
        return str(RAW_DATA)

    @task
    def analyze_data(input_file: str) -> str:
        subprocess.run(
            [
                sys.executable,
                str(ML_ROOT / "prepare_dataset.py"),
                "analyze",
                "--input",
                input_file,
                "--output-dir",
                str(ANALYSIS_DATA),
                "--timezone",
                "America/Sao_Paulo",
            ],
            check=True,
        )
        return str(ANALYSIS_DATA / "eda_report.json")

    @task
    def prepare_data(input_file: str, _report_file: str) -> str:
        subprocess.run(
            [
                sys.executable,
                str(ML_ROOT / "prepare_dataset.py"),
                "prepare",
                "--input",
                input_file,
                "--output-dir",
                str(PREPARED_DATA),
                "--timezone",
                "America/Sao_Paulo",
            ],
            check=True,
        )
        return str(PREPARED_DATA)

    raw_file = generate_data()
    report_file = analyze_data(raw_file)
    prepare_data(raw_file, report_file)


mock_telemetry_pipeline()
