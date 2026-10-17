FROM python:3.12-slim
WORKDIR /app
COPY integration/ /app/integration/
ENV PYTHONUNBUFFERED=1
CMD ["python", "integration/pilot_server.py"]
