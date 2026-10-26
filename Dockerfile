# Serves the Flask API with gunicorn. Build: docker build -t sales-forecast-api .
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY forecasting/ forecasting/
COPY api/ api/
COPY models/ models/
COPY data/processed/sales_history.parquet data/processed/sales_history.parquet
ENV PORT=8000
EXPOSE 8000
CMD gunicorn --chdir api --bind 0.0.0.0:$PORT --workers 2 --timeout 120 app:app
