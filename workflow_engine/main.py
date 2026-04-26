import uvicorn

from workflow_engine.app import create_app
from workflow_engine.bootstrap import build_dependencies
from workflow_engine.config import Settings


def main() -> None:
    settings = Settings()
    deps = build_dependencies(settings)
    app = create_app(deps)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
