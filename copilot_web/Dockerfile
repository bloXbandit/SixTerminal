FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk \
    gcc \
    python3-dev \
    libfontconfig1 \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"
ENV JDK_HOME=${JAVA_HOME}
ENV JAVA_INCLUDE_PATH=${JAVA_HOME}/include

WORKDIR /app

COPY requirements.txt .
RUN echo "cache-bust-$(date)" && pip install --no-cache-dir JPype1 && pip install --no-cache-dir xerparser==0.13.9 && pip install --no-cache-dir -r requirements.txt

COPY . .

# Build-time PDF extraction: convert all PDFs to .txt sidecar files
# This eliminates runtime PDF parsing delays and timeouts
RUN echo "Extracting PDF text at build time..." && \
    python extract_pdfs.py || echo "Some PDFs may have failed extraction, continuing..."

EXPOSE 5000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "120"]
