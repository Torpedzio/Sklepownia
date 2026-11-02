FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
ARG DEV=0
COPY requirements.txt requirements-dev.txt ./
RUN if [ "$DEV" = "1" ]; then pip install --no-cache-dir -r requirements-dev.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi
COPY . .
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
