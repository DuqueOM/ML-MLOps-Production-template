"""Integration tests for {ServiceName} ML service.

Validates the full running service: health, predictions, SHAP, metrics.
Requires the service to be running before executing.

Usage:
    pytest tests/integration/test_service_integration.py -v
"""

import requests
import pytest

# TODO: Replace with your service's actual URL
SERVICE_URL = "http://localhost:8000"
TIMEOUT = 10

# TODO: Replace with a valid prediction payload for your service
SAMPLE_PAYLOAD = {
    "feature_a": 42.0,
    "feature_b": 50000.0,
    "feature_c": "category_A",
}


class TestHealthEndpoints:
    """Test service health and readiness."""

    def test_health_endpoint(self):
        """Service /health returns 200 with expected fields."""
        response = requests.get(f"{SERVICE_URL}/health", timeout=TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["ok", "healthy"]

    def test_model_loaded(self):
        """Service reports model is loaded."""
        response = requests.get(f"{SERVICE_URL}/health", timeout=TIMEOUT)
        data = response.json()
        assert data.get("model_loaded") is True, "Model not loaded — check init container or model path"

    def test_metrics_endpoint(self):
        """Prometheus /metrics endpoint is available."""
        response = requests.get(f"{SERVICE_URL}/metrics", timeout=TIMEOUT)
        assert response.status_code == 200
        assert "predictions_total" in response.text or "HELP" in response.text


class TestPredictionEndpoint:
    """Test the /predict endpoint."""

    def test_predict_returns_200(self):
        """Valid payload returns 200."""
        response = requests.post(
            f"{SERVICE_URL}/predict",
            json=SAMPLE_PAYLOAD,
            timeout=TIMEOUT,
        )
        assert response.status_code == 200

    def test_predict_response_schema(self):
        """Response contains expected fields."""
        response = requests.post(
            f"{SERVICE_URL}/predict",
            json=SAMPLE_PAYLOAD,
            timeout=TIMEOUT,
        )
        data = response.json()
        # TODO: Replace with your actual response fields
        assert "prediction" in data or "probability" in data

    def test_predict_with_shap(self):
        """Prediction with SHAP explanation."""
        response = requests.post(
            f"{SERVICE_URL}/predict?explain=true",
            json=SAMPLE_PAYLOAD,
            timeout=TIMEOUT,
        )
        assert response.status_code == 200
        data = response.json()
        assert "shap_values" in data or "explanation" in data

    def test_predict_invalid_payload(self):
        """Invalid payload returns 422."""
        response = requests.post(
            f"{SERVICE_URL}/predict",
            json={"invalid": "data"},
            timeout=TIMEOUT,
        )
        assert response.status_code == 422

    def test_predict_latency_sla(self):
        """Prediction latency is within SLA (< 500ms without SHAP)."""
        import time

        start = time.time()
        response = requests.post(
            f"{SERVICE_URL}/predict",
            json=SAMPLE_PAYLOAD,
            timeout=TIMEOUT,
        )
        latency_ms = (time.time() - start) * 1000
        assert response.status_code == 200
        assert latency_ms < 500, f"Prediction took {latency_ms:.0f}ms (SLA: <500ms)"


class TestModelInfo:
    """Test model metadata endpoint."""

    def test_model_info(self):
        """/model/info returns model metadata."""
        response = requests.get(f"{SERVICE_URL}/model/info", timeout=TIMEOUT)
        if response.status_code == 404:
            pytest.skip("No /model/info endpoint — optional")
        assert response.status_code == 200
        data = response.json()
        # Expect at least version or hash
        assert "version" in data or "model_hash" in data or "model_path" in data
