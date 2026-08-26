FROM python:3.11-slim
WORKDIR /app
ENV PYTHONPATH=src PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src src
COPY templates templates
COPY static static
COPY docs docs
ENV ABU_ALIA_RESTORE_ON_BOOT=true
EXPOSE 8080
CMD ["sh", "-c", "python -m abu_alia restore-catalog && python -m abu_alia serve --host 0.0.0.0 --port ${PORT:-8080}"]
