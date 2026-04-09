FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-11-jre-headless \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
# cache-bust: 2026-04-09
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium

COPY . .

EXPOSE 5000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "120"]
