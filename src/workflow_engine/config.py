from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mock_api_base_url: str = "http://localhost:8080"
    mock_api_key: str = "mock-api-key-12345"
    llm_provider: str = "fake"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    class Config:
        env_file = ".env"
