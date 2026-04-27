import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.bootstrap import build_test_dependencies


@pytest.fixture
def deps():
    return build_test_dependencies()


@pytest.fixture
def client(deps):
    return TestClient(create_app(deps))
