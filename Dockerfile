FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install --no-install-recommends -y \
    ffmpeg imagemagick fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*

# Allow ImageMagick to process all file types
RUN sed -i 's/<policy domain="path".*/<policy domain="path" rights="read|write" pattern="@*"\/>/' \
    /etc/ImageMagick-6/policy.xml 2>/dev/null || true

WORKDIR /app

COPY pyproject.toml .
RUN uv pip install --system -r pyproject.toml

COPY Backend/ /app/Backend/
COPY Frontend/ /app/Frontend/
COPY fonts/ /app/fonts/
