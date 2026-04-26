import pytest
from fastapi.testclient import TestClient

from workflow_engine.app import create_app
from workflow_engine.bootstrap import build_test_dependencies


@pytest.fixture
def deps():
    return build_test_dependencies()


@pytest.fixture
def client(deps):
    return TestClient(create_app(deps))
