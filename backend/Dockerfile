FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir uv && apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src ./src
RUN uv pip install --system --no-cache . 
EXPOSE 8000
CMD ["eb", "serve"]
