FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    # Tokenizer data for the sentence splitter, baked into the image below.
    NLTK_DATA=/usr/local/share/nltk_data \
    # Embedding model cache; docker-compose mounts a volume here so the model
    # is downloaded once, not on every container start.
    FASTEMBED_CACHE_PATH=/models

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (before other files)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# NLTK tokenizer used by create_db. nltk.download() reports failure by
# returning False, so turn that into a failed build.
# Behind an HTTP proxy, build with --build-arg NLTK_ALLOW_PROXIED_URLOPEN=1.
ARG NLTK_ALLOW_PROXIED_URLOPEN
RUN python -c "import nltk, sys; sys.exit(0 if nltk.download('punkt_tab', download_dir='$NLTK_DATA', quiet=True) else 1)"

# Copy entire project
COPY . .

# Create necessary directories
RUN mkdir -p logs chroma_db data /models

# Expose ports
EXPOSE 8000 8501

# Default command (API)
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
