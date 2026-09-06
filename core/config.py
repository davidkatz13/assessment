from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Static configuration for the batch document processor, sourced from the environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "marvelx"

    upload_dir: str = "./data/uploads"
    max_batch_file_size_bytes: int = 25 * 1024 * 1024
    max_claims_per_batch: int = 5_000
    max_reported_errors: int = 200
    log_level: str = "INFO"
    cors_allowed_origins: str = "http://localhost:3000"

    @property
    def database_url(self) -> URL:
        """Build the SQLAlchemy connection URL from the individual Postgres settings above."""
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        """cors_allowed_origins, split into a list for CORSMiddleware."""
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
