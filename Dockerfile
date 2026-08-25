FROM python:3.11-slim
WORKDIR /app
ENV PYTHONPATH=src PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src src
COPY templates templates
COPY static static
COPY docs docs
EXPOSE 8080
CMD ["python", "-m", "abu_alia", "serve", "--host", "0.0.0.0", "--port", "8080"]
