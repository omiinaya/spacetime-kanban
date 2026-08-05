from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    stdb_host: str = "localhost"
    stdb_port: int = 3001
    stdb_db: str = "kanban"
    server_port: int = 8727
    cors_origin: str = "http://localhost:4444"
    github_token: str = ""
    github_default_repo: str = ""
    api_key: str = ""  # Set API_KEY env var to require auth on mutation endpoints

    # ── Auto-star ──
    # On first install, star the project's GitHub repo (best-effort) when a
    # token is configured and the user isn't the owner / hasn't starred it.
    auto_star_enabled: bool = True

    # ── Scheduler (background tasks inside server process) ──
    scheduler_enabled: bool = True
    dispatcher_interval_seconds: int = 5
    stale_check_interval_seconds: int = 120
    dead_board_interval_seconds: int = 3600  # Don't restart too often — workers need time
    template_interval_seconds: int = 900
    metrics_interval_seconds: int = 900
    scanner_interval_seconds: int = 1800  # Run repo scanners every 30 minutes
    improver_interval_seconds: int = 3600  # Self-improvement checker every 1 hour
    remediator_interval_seconds: int = 3600  # Blocked-task remediation every 1 hour

    # ── Webhook alerts ──
    webhook_default_url: str = ""  # Default alert destination (Discord, Slack, etc.)
    webhook_max_retries: int = 3
    webhook_timeout_seconds: int = 10

    # ── Worker adapter ──
    worker_command: str = "python3"
    worker_script: str = ""  # Path to worker entry point script (absolute or relative to server/)
    worker_args: str = ""  # Extra args passed to worker_command (e.g. "-m server.workers.run")
    min_workers: int = 2
    max_workers: int = 8
    max_memory_pct: int = 80
    stale_minutes: int = 45  # Must exceed LLM worker timeout to avoid race

    # ── Agent identity ──
    agent_id: str = "hermes"

    @property
    def stdb_base_url(self) -> str:
        return f"http://{self.stdb_host}:{self.stdb_port}"

    @property
    def stdb_sql_url(self) -> str:
        return f"{self.stdb_base_url}/v1/database/{self.stdb_db}/sql"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
