FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY generate_mock_data.py ./generate_mock_data.py

CMD ["python", "generate_mock_data.py"]
