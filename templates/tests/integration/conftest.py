"""Integration test configuration for {ServiceName}.

These tests validate the full service stack (API + model + dependencies).
Requires the service to be running (e.g., via docker-compose or make serve).

Usage:
    # Start the service first
    docker compose -f docker-compose.demo.yml up -d
    # Or: make serve (in another terminal)

    # Run integration tests
    pytest tests/integration/ -v
"""

import time

import pytest
import requests

# TODO: Replace with your service's actual URL and port
SERVICE_URL = "http://localhost:8000"
MLFLOW_URL = "http://localhost:5000"
TIMEOUT = 5


def wait_for_service(url: str, timeout: int = 120) -> bool:
    """Wait for a service to become healthy."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(f"{url}/health", timeout=TIMEOUT)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    return False


@pytest.fixture(scope="session", autouse=True)
def ensure_service_healthy():
    """Ensure the ML service is running before tests."""
    if not wait_for_service(SERVICE_URL, timeout=60):
        pytest.skip(f"Service at {SERVICE_URL} is not healthy — skipping integration tests")
