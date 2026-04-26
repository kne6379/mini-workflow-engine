from fastapi import FastAPI

from workflow_engine.api.routes import register_routes
from workflow_engine.bootstrap import AppDependencies


def create_app(deps: AppDependencies) -> FastAPI:
    app = FastAPI(
        title="AI 워크플로우 실행 엔진",
        description="고객 문의 자동 응답 워크플로우를 실행하고 승인 대기 상태를 관리하는 API입니다.",
        version="0.1.0",
    )
    register_routes(app, deps)
    return app
