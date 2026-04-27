from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    mock_api_base_url: str = "http://localhost:8080"
    mock_api_key: str = "mock-api-key-12345"
    openai_api_key: str
    openai_model: str = "gpt-4.1-mini"           # fallback
    openai_classify_model: str = ""              # 비면 openai_model 사용
    openai_generate_model: str = ""              # 비면 openai_model 사용
    openai_temperature: float = 0.0

    @property
    def classify_model(self) -> str:
        return self.openai_classify_model or self.openai_model

    @property
    def generate_model(self) -> str:
        return self.openai_generate_model or self.openai_model
