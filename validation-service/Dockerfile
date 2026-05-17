FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY validation-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY shared /app/shared
COPY validation-service/app /app/app
ENV PYTHONPATH=/app
EXPOSE 8502
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8502"]
