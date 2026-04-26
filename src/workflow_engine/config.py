from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    mock_api_base_url: str = "http://localhost:8080"
    mock_api_key: str = "mock-api-key-12345"
    llm_provider: str = "fake"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
