from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Polza.ai
    POLZA_API_KEY: str | None = None
    POLZA_BASE_URL: str = "https://polza.ai/api/v1"
    LLM_MODEL_ANALYSIS: str = "openai/gpt-4o-mini"

    # Web search (Gemini 3 Flash by user request; can be overridden)
    WEB_SEARCH_MODEL: str = "google/gemini-3-flash-preview"
    WEB_SEARCH_MAX_RESULTS: int = 3

    # Diff settings
    DIFF_UNIFIED_CONTEXT_LINES: int = 3
    POINT_MERGE_MAX_DISTANCE_LINES: int = 6

    # Concurrency
    MAX_PARALLEL_POINTS: int = 3

    # Output size limits for front-end payload
    MAX_POINT_CONTEXT_CHARS: int = 4000

    # Apache Tika (для извлечения текста из DOCX/PDF)
    # По умолчанию tika-python пытается скачать tika-server.jar при первом использовании.
    # Если в окружении есть проблемы с SSL/интернетом — укажи локальный jar/папку.
    TIKA_SERVER_JAR: str | None = None  # например "/path/to/tika-server.jar"
    TIKA_PATH: str | None = None  # директория, где лежит tika-server.jar (+ подписи .md5/.sha512 при необходимости)
    TIKA_SERVER_ENDPOINT: str | None = None  # например "http://localhost:9998"
    TIKA_CLIENT_ONLY: bool = False  # True => предполагаем, что сервер уже запущен


settings = Settings()

