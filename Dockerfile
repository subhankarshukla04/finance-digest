# Batch job: generates the daily digest and exits. Not a long-running service.
FROM python:3.11.9-slim-bookworm

WORKDIR /app

# No extra system packages: feedparser + requests are pure-Python wheels,
# no compiler or native lib needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY digest.py .

# Secrets (GROQ_API_KEY, NEWS_API_KEY, BARK_KEY) and DIGEST_URL are read
# from the environment at runtime via `docker run -e` or `--env-file`.
# Never baked into the image.

ENTRYPOINT ["python", "digest.py"]
