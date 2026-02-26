"""Pydantic schemas for API request/response models."""

import re
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

# Reusable validation patterns
_SAFE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_DOMAIN_PATTERN = re.compile(
    r"^(\*\.)?[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$"
)
_GIT_REPO_PATTERN = re.compile(
    r"^https://[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?"
    r"(\.[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?)*"
    r"(:[0-9]{1,5})?"
    r"(/[a-zA-Z0-9._~:@!$&'()*+,;=%-]*)+"
    r"\.git$"
)


def _validate_safe_name(v: str) -> str:
    if not _SAFE_NAME_PATTERN.match(v):
        raise ValueError("Only alphanumeric characters, dots, hyphens, and underscores allowed")
    return v


def _validate_git_repo_url(v: str | None) -> str | None:
    if v is None:
        return v
    if not _GIT_REPO_PATTERN.match(v):
        raise ValueError(
            "git_repo must be an HTTPS URL ending with .git (e.g. https://github.com/user/repo.git)"
        )
    hostname = urlparse(v).hostname or ""
    _blocked_prefixes = ("localhost", "127.", "0.0.0.0", "169.254.", "10.")
    if any(hostname.startswith(b) for b in _blocked_prefixes):
        raise ValueError("git_repo must not point to localhost or private addresses")
    if hostname.endswith(".local") or hostname == "::1":
        raise ValueError("git_repo must not point to localhost or private addresses")
    parts = hostname.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        first, second = int(parts[0]), int(parts[1])
        if first == 172 and 16 <= second <= 31:
            raise ValueError("git_repo must not point to private addresses")
        if first == 192 and second == 168:
            raise ValueError("git_repo must not point to private addresses")
    return v


# ── Server ──────────────────────────────────────────────


class ServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    host: str = Field(..., min_length=1, max_length=255)
    user: str = "root"
    port: int = Field(default=22, ge=1, le=65535)
    ssh_key_path: str | None = None
    provider: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_safe_name(v)


class ServerUpdate(BaseModel):
    host: str | None = Field(default=None, max_length=255)
    user: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    ssh_key_path: str | None = None
    provider: str | None = None


class ServerOut(BaseModel):
    id: int
    name: str
    host: str
    user: str
    port: int
    ssh_key_path: str | None
    status: str
    provider: str | None
    created_at: datetime
    updated_at: datetime
    app_count: int = 0
    tags: list[str] = []

    model_config = {"from_attributes": True}


class MemoryUsage(BaseModel):
    total: str
    used: str
    free: str
    percent: float


class DiskUsage(BaseModel):
    total: str
    used: str
    free: str
    percent: float


class ServerContainerInfo(BaseModel):
    id: str
    name: str
    status: str
    image: str = ""


class ServerStatus(BaseModel):
    name: str
    host: str
    uptime: str
    memory: MemoryUsage | None = None
    disk: DiskUsage | None = None
    cpu: float | None = None
    containers: list[ServerContainerInfo] = []


class ServerMetricOut(BaseModel):
    id: int
    server_id: int
    recorded_at: datetime
    cpu_percent: float | None
    mem_percent: float | None
    disk_percent: float | None

    model_config = {"from_attributes": True}


# ── App ─────────────────────────────────────────────────


class AppCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    server_name: str
    domain: str | None = None
    port: int = Field(default=3000, ge=1, le=65535)
    git_repo: str | None = None
    branch: str = "main"
    image: str | None = None
    cpu_limit: str | None = None
    memory_limit: str | None = None
    health_check_url: str | None = None
    health_check_interval: int | None = None
    replicas: int = 1
    deploy_strategy: str = "restart"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_safe_name(v)

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str | None) -> str | None:
        if v is not None and not _DOMAIN_PATTERN.match(v):
            raise ValueError("Invalid domain name format")
        return v

    @field_validator("git_repo")
    @classmethod
    def validate_git_repo(cls, v: str | None) -> str | None:
        return _validate_git_repo_url(v)


class AppUpdate(BaseModel):
    domain: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    git_repo: str | None = None
    branch: str | None = None
    image: str | None = None
    cpu_limit: str | None = None
    memory_limit: str | None = None
    health_check_url: str | None = None
    health_check_interval: int | None = None
    replicas: int | None = None
    deploy_strategy: str | None = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str | None) -> str | None:
        if v is not None and not _DOMAIN_PATTERN.match(v):
            raise ValueError("Invalid domain name format")
        return v

    @field_validator("git_repo")
    @classmethod
    def validate_git_repo(cls, v: str | None) -> str | None:
        return _validate_git_repo_url(v)


class AppOut(BaseModel):
    id: int
    name: str
    server_id: int
    server_name: str = ""
    domain: str | None
    port: int
    git_repo: str | None
    branch: str
    image: str | None
    status: str
    app_type: str
    cpu_limit: str | None = None
    memory_limit: str | None = None
    health_check_url: str | None = None
    health_check_interval: int | None = None
    replicas: int = 1
    deploy_strategy: str = "restart"
    dependencies: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeploymentOut(BaseModel):
    id: int
    app_id: int
    commit_hash: str | None
    image_used: str | None = None
    status: str
    log: str | None
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class AppLogs(BaseModel):
    app_name: str
    logs: str


# ── Env ─────────────────────────────────────────────────


class EnvVarSet(BaseModel):
    key: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    value: str


class EnvVarOut(BaseModel):
    key: str
    value: str  # masked unless ?show_values=true


# ── Database ────────────────────────────────────────────


class DatabaseCreate(BaseModel):
    server_name: str
    name: str = Field(..., min_length=1, max_length=100)
    db_type: str  # postgres, mysql, redis, mongo
    version: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_safe_name(v)


class DatabaseOut(BaseModel):
    id: int
    name: str
    server_name: str
    db_type: str
    port: int
    status: str
    backup_schedule: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class BackupFileOut(BaseModel):
    filename: str
    size: str
    size_bytes: int
    modified: str


class DatabaseRestore(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    server_name: str | None = None


class BackupScheduleCreate(BaseModel):
    cron_expression: str = Field(..., min_length=5, max_length=100)
    retention_days: int = Field(default=7, ge=1, le=365)

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError("Cron expression must have exactly 5 fields")
        return v.strip()


# ── Proxy ───────────────────────────────────────────────


class ProxyRoute(BaseModel):
    domain: str
    port: int = Field(..., ge=1, le=65535)


class ProxyRouteCreate(BaseModel):
    domain: str
    port: int = Field(..., ge=1, le=65535)
    server_name: str

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        if not _DOMAIN_PATTERN.match(v) or len(v) > 253:
            raise ValueError("Invalid domain name format")
        return v


# ── Health ──────────────────────────────────────────────


class ContainerHealth(BaseModel):
    name: str
    state: str  # running, exited, restarting, paused, dead
    status: str  # human-readable Docker status string
    image: str = ""
    health: str = ""  # healthy, unhealthy, starting, or empty


class AppHealthCheckResult(BaseModel):
    healthy: bool
    status_code: int | None = None
    response_time_ms: float | None = None
    error: str | None = None


class AppHealth(BaseModel):
    app_name: str
    db_status: str
    actual_status: str
    status_mismatch: bool
    containers: list[ContainerHealth]
    http_health: AppHealthCheckResult | None = None
    checked_at: datetime


class DatabaseStats(BaseModel):
    disk_size: str | None = None
    active_connections: int | None = None
    version: str | None = None
    uptime: str | None = None


# ── Dashboard ───────────────────────────────────────────


class DashboardStats(BaseModel):
    total_servers: int
    active_servers: int
    total_apps: int
    running_apps: int
    total_databases: int
    recent_deployments: list[DeploymentOut]


# ── Webhooks ───────────────────────────────────────────

VALID_WEBHOOK_EVENTS = [
    "deploy.success",
    "deploy.failure",
    "backup.complete",
    "backup.restore",
    "health.down",
    "health.up",
]


class WebhookCreate(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    events: list[str]
    secret: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        invalid = [e for e in v if e not in VALID_WEBHOOK_EVENTS]
        if invalid:
            raise ValueError(f"Invalid events: {invalid}")
        if not v:
            raise ValueError("At least one event is required")
        return v


class WebhookOut(BaseModel):
    id: int
    url: str
    events: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── SSH Keys ──────────────────────────────────────────


class SSHKeyGenerate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_safe_name(v)


class SSHKeyDeploy(BaseModel):
    server_name: str


# ── Server Tags ──────────────────────────────────────────


class ServerTagCreate(BaseModel):
    tag: str = Field(..., min_length=1, max_length=100)


# ── App Dependencies ─────────────────────────────────────


class AppDependencyCreate(BaseModel):
    depends_on: str = Field(..., min_length=1, max_length=100)


class AppDependencyOut(BaseModel):
    id: int
    app_name: str
    depends_on_app_name: str


class ScaleInput(BaseModel):
    replicas: int = Field(..., ge=1, le=100)


class SSHKeyOut(BaseModel):
    id: int
    name: str
    fingerprint: str
    key_type: str
    public_key: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── GitHub ─────────────────────────────────────────────


class GitHubConnect(BaseModel):
    token: str = Field(..., min_length=1)


class GitHubStatus(BaseModel):
    connected: bool
    username: str | None = None


class GitHubRepo(BaseModel):
    full_name: str
    name: str
    private: bool
    default_branch: str
    description: str = ""
    html_url: str
    clone_url: str
    owner: dict[str, str]
