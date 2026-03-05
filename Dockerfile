FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium && playwright install-deps chromium

COPY . .

RUN mkdir -p output logs

EXPOSE 8888

ENV PORT=8888

CMD ["python", "app.py"]
