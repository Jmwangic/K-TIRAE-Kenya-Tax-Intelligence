FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY db ./db
COPY scripts/deploy_entrypoint.py ./scripts/deploy_entrypoint.py

ENV PYTHONUNBUFFERED=1

CMD ["python", "scripts/deploy_entrypoint.py"]
