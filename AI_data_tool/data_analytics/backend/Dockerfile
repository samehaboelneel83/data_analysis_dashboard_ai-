FROM python:3.12-slim
WORKDIR /app
# mdbtools reads Microsoft Access (.mdb/.accdb). Microsoft's own ACE/Jet
# provider is Windows-only, so on this image it is the only way to read Access
# at all. Debian bookworm ships 1.0.0, the release that added .accdb support.
# Needed at BUILD time only -- the running container makes no network calls.
RUN apt-get update && apt-get install -y --no-install-recommends freetds-dev mdbtools && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
