from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Printer connection
    PRINTER_HOST: str = "printer.local.mesh"
    PRINTER_PORT: int = 9100
    PRINTER_TIMEOUT: int = 5
    PRINTER_RETRY_MAX: int = 2

    # Printer features
    ENABLE_CUT: bool = True
    PAPER_WIDTH_CHARS: int = 48

    # Station identity
    NODE_CALLSIGN: str = "NOCALL"
    SERVER_HOST: str = ""  # e.g. "mynode-webserver.local.mesh" — shown in footer

    # Security
    ADMIN_PASSWORD: str = "changeme"
    SECRET_KEY: str = "change-this-to-a-random-string"

    # Database
    DATABASE_PATH: str = "data/printqueue.db"

    # Rate limiting
    RATE_LIMIT_PRINTS: str = "10/minute"
    MAX_QUEUE_SIZE: int = 100
    MAX_MESSAGE_LENGTH: int = 1000

    # App
    APP_VERSION: str = "1.0.0"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
