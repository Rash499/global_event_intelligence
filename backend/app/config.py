from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Global Event Intelligence API"
    database_url: str = "sqlite:///./data/events.db"
    ollama_enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    gdelt_max_records: int = 50
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
