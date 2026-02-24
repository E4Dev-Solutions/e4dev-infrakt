# =============================================================================
# Stage 1 — frontend-build
# Compiles the React/TypeScript dashboard into a static dist/ directory.
# This stage is discarded after the build; none of its contents (node_modules,
# TypeScript toolchain, etc.) end up in the final image.
# =============================================================================
FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend

# Copy dependency manifests first so Docker can cache the npm install layer.
# The source files change far more frequently than package.json, so separating
# these two COPY instructions means npm ci only re-runs when deps actually change.
COPY frontend/package.json frontend/package-lock.json ./

RUN npm ci --prefer-offline

# Copy the full frontend source now that deps are installed.
COPY frontend/ ./

# tsc -b runs the TypeScript compiler, then vite build produces the dist/.
RUN npm run build


# =============================================================================
# Stage 2 — runtime
# Minimal Python image that runs the FastAPI/uvicorn server and serves the
# pre-built frontend as static files.
# =============================================================================
FROM python:3.13-slim AS runtime

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
# so logs appear immediately in `docker logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system packages needed at runtime only:
#   - libpq-dev is NOT needed (we use SQLite, not Postgres)
#   - openssh-client is needed because paramiko shells out to ssh for deployments
#   - ca-certificates ensures TLS works when the app calls external APIs
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openssh-client \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user. Running as root inside a container is a security
# risk — if the process is exploited, the attacker has root inside the container
# and can potentially escape to the host.
RUN useradd --create-home --shell /bin/bash infrakt

WORKDIR /app

# Install Python dependencies from pyproject.toml.
# Copy only the build descriptor first so pip install is cached unless
# pyproject.toml changes, even if application source changes.
COPY pyproject.toml README.md ./

# Install the package in non-editable mode. pip resolves [project.dependencies]
# from pyproject.toml. We do NOT install the [dev] extras (pytest, mypy, ruff)
# because they have no place in a production image.
RUN pip install --no-cache-dir .

# Copy Python application source.
# cli/ and api/ are the two packages listed in [tool.hatch.build.targets.wheel].
COPY cli/ ./cli/
COPY api/ ./api/

# Copy the compiled frontend from the build stage.
# api/main.py resolves FRONTEND_DIST as:
#   Path(__file__).parent.parent / "frontend" / "dist"
# __file__ is /app/api/main.py → parent.parent is /app → so this must land at
# /app/frontend/dist for the StaticFiles mount to activate.
COPY --from=frontend-build /build/frontend/dist ./frontend/dist/

# Transfer ownership of the working directory to the non-root user so the
# application can create the .infrakt state directory inside the mounted volume.
RUN chown -R infrakt:infrakt /app

USER infrakt

# Document the port the server listens on. This does not publish the port —
# that happens in docker-compose or `docker run -p`.
EXPOSE 8000

# Health check: hit the FastAPI /docs endpoint (always present) to verify
# the server is accepting connections. Fail after 3 missed checks.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

# Use exec form (JSON array) so the process is PID 1 and receives SIGTERM
# directly, enabling graceful shutdown.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
