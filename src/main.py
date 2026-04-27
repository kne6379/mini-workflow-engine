import uvicorn

from src.app import create_app
from src.bootstrap import build_dependencies
from src.config import Settings


def main() -> None:
    settings = Settings()
    deps = build_dependencies(settings)
    app = create_app(deps)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
