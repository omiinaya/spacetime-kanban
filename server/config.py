from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    stdb_host: str = "localhost"
    stdb_port: int = 3001
    stdb_db: str = "spacetimedb-kanban"
    server_port: int = 8725
    cors_origin: str = "http://localhost:5189"

    @property
    def stdb_base_url(self) -> str:
        return f"http://{self.stdb_host}:{self.stdb_port}"

    @property
    def stdb_sql_url(self) -> str:
        return f"{self.stdb_base_url}/v1/database/{self.stdb_db}/sql"

    model_config = {"env_file": ".env"}

settings = Settings()
