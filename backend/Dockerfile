FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# DejaVu: a font with Polish letters for invoice PDFs.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
ARG DEV=0
COPY requirements.txt requirements-dev.txt ./
RUN if [ "$DEV" = "1" ]; then pip install --no-cache-dir -r requirements-dev.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi
COPY . .
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
