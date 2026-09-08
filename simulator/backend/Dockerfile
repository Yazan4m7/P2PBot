FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY p2psim ./p2psim
RUN pip install --no-cache-dir ".[postgres]"
RUN mkdir -p /app/data
EXPOSE 8090
CMD ["uvicorn", "p2psim.api:app", "--host", "0.0.0.0", "--port", "8090"]
