FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY generate_mock_data.py build_real_dataset.py ./
COPY collection/bench-calibration-v1.json ./collection/bench-calibration-v1.json

CMD ["python", "build_real_dataset.py", "--calibration"]
