FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[postgres]"
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["uvicorn", "p2pbot.api:app", "--host", "0.0.0.0", "--port", "8000"]
