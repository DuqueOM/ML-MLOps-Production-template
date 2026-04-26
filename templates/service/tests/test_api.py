"""API endpoint tests for {ServiceName}.

Real integration tests using FastAPI TestClient and the mocked-model
fixtures from ``conftest.py``. Covers:

- liveness `/health` and readiness `/ready` (D-23)
- single prediction `/predict` (+ ?explain=true SHAP path)
- batch prediction `/predict_batch`
- Prometheus `/metrics`
- model metadata `/model/info`
- error handling (422 on invalid input)

How to run:
    pytest tests/test_api.py -v
    pytest tests/test_api.py -v -k "predict"

Customization checklist after scaffolding:
    1. Replace `feature_a/b/c` with your real feature names everywhere.
    2. Adjust `valid_payload` in conftest.py to your schema.
    3. If you add new endpoints, add a corresponding test class here.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Liveness `/health`
# ---------------------------------------------------------------------------
class TestHealthEndpoint:
    """Liveness probe — must always return 200 once the process is alive."""

    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_includes_status(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert data["status"] == "healthy"

    def test_health_includes_version(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert "version" in data
        assert isinstance(data["version"], str)


# ---------------------------------------------------------------------------
# Readiness `/ready` (D-23)
# ---------------------------------------------------------------------------
class TestReadyEndpoint:
    """Readiness probe — 503 until BOTH model loaded and warm-up done."""

    def test_ready_returns_200_when_loaded(self, client: TestClient) -> None:
        # The conftest fixture pre-populates _model_pipeline + _warmed_up.
        response = client.get("/ready")
        assert response.status_code == 200

    def test_ready_payload_shape(self, client: TestClient) -> None:
        data = client.get("/ready").json()
        assert data["status"] in ("ready", "not_ready")
        assert "model_loaded" in data
        assert "warmed_up" in data
        assert "version" in data


# ---------------------------------------------------------------------------
# Single prediction `/predict`
# ---------------------------------------------------------------------------
class TestPredictEndpoint:
    """Tests for /predict — happy path + validation errors."""

    def test_predict_returns_200(self, client: TestClient, valid_payload: dict) -> None:
        response = client.post("/predict", json=valid_payload)
        assert response.status_code == 200, response.text

    def test_predict_returns_required_fields(self, client: TestClient, valid_payload: dict) -> None:
        data = client.post("/predict", json=valid_payload).json()
        for field in ("prediction_id", "prediction_score", "risk_level", "model_version"):
            assert field in data, f"missing field {field} in response: {data}"

    def test_predict_score_in_unit_interval(self, client: TestClient, valid_payload: dict) -> None:
        data = client.post("/predict", json=valid_payload).json()
        assert 0.0 <= data["prediction_score"] <= 1.0

    def test_predict_risk_level_enum(self, client: TestClient, valid_payload: dict) -> None:
        data = client.post("/predict", json=valid_payload).json()
        assert data["risk_level"] in ("LOW", "MEDIUM", "HIGH")

    def test_predict_missing_fields_422(self, client: TestClient) -> None:
        response = client.post("/predict", json={})
        assert response.status_code == 422

    def test_predict_wrong_type_422(self, client: TestClient, valid_payload: dict) -> None:
        bad = {**valid_payload, "feature_a": "not_a_number"}
        response = client.post("/predict", json=bad)
        assert response.status_code == 422

    def test_predict_missing_entity_id_422(self, client: TestClient, valid_payload: dict) -> None:
        bad = {k: v for k, v in valid_payload.items() if k != "entity_id"}
        response = client.post("/predict", json=bad)
        assert response.status_code == 422

    def test_predict_with_explain_true_returns_explanation(self, client: TestClient, valid_payload: dict) -> None:
        """The ?explain=true path triggers SHAP. Mock explainer may yield
        an Explanation with detail='unavailable'; we only assert presence
        of the explanation key (D-04, D-24)."""
        response = client.post("/predict?explain=true", json=valid_payload)
        assert response.status_code == 200
        data = response.json()
        # `explanation` is Optional in the schema; accept either an object
        # (KernelExplainer ran) or a "unavailable" stub.
        assert "explanation" in data


# ---------------------------------------------------------------------------
# Batch prediction `/predict_batch`
# ---------------------------------------------------------------------------
class TestBatchPredictEndpoint:
    """Tests for /predict_batch (note: underscore, not slash)."""

    def test_batch_returns_200(self, client: TestClient, batch_payload: dict) -> None:
        response = client.post("/predict_batch", json=batch_payload)
        assert response.status_code == 200, response.text

    def test_batch_returns_correct_count(self, client: TestClient, batch_payload: dict) -> None:
        data = client.post("/predict_batch", json=batch_payload).json()
        assert data["total_customers"] == len(batch_payload["customers"])
        assert len(data["predictions"]) == len(batch_payload["customers"])

    def test_batch_predictions_have_required_fields(self, client: TestClient, batch_payload: dict) -> None:
        data = client.post("/predict_batch", json=batch_payload).json()
        for pred in data["predictions"]:
            for field in ("prediction_id", "prediction_score", "risk_level"):
                assert field in pred

    def test_batch_empty_returns_422(self, client: TestClient) -> None:
        response = client.post("/predict_batch", json={"customers": []})
        assert response.status_code == 422

    def test_batch_missing_customers_key_422(self, client: TestClient) -> None:
        response = client.post("/predict_batch", json={})
        assert response.status_code == 422

    def test_batch_too_many_returns_422(self, client: TestClient, valid_payload: dict) -> None:
        # Schema enforces max_length=1000.
        too_many = {"customers": [valid_payload] * 1001}
        response = client.post("/predict_batch", json=too_many)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Metrics `/metrics`
# ---------------------------------------------------------------------------
class TestMetricsEndpoint:
    """Prometheus exposition format checks."""

    def test_metrics_returns_200(self, client: TestClient) -> None:
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type_is_prometheus(self, client: TestClient) -> None:
        response = client.get("/metrics")
        # prometheus_client uses text/plain with version=0.0.4
        assert "text/plain" in response.headers.get("content-type", "")

    def test_metrics_includes_request_counter(self, client: TestClient, valid_payload: dict) -> None:
        # Hit /predict once to ensure the counter has been incremented.
        client.post("/predict", json=valid_payload)
        body = client.get("/metrics").text
        assert "requests_total" in body

    def test_metrics_includes_latency_histogram(self, client: TestClient, valid_payload: dict) -> None:
        client.post("/predict", json=valid_payload)
        body = client.get("/metrics").text
        assert "request_latency" in body or "request_duration" in body

    def test_metrics_contract_matches_slo_prometheusrule(self, client: TestClient, valid_payload: dict) -> None:
        """Pin the exact metric names + labels the SLO PrometheusRule depends on.

        ``k8s/base/slo-prometheusrule.yaml`` queries:

            <prefix>_requests_total{status=~"5.."}
            <prefix>_request_duration_seconds_bucket{le="0.5"}
            <prefix>_request_duration_seconds_count

        Where ``<prefix>`` is the value of ``SERVICE_METRIC_PREFIX``
        (set by the scaffolder + deployment.yaml). If any of these
        change shape, every burn-rate alert silently goes blind \u2014 so
        we assert the exact tokens here, not just substrings.
        """
        import os
        import re

        client.post("/predict", json=valid_payload)
        body = client.get("/metrics").text

        prefix = os.getenv("SERVICE_METRIC_PREFIX", "ml_service").replace("-", "_")

        # 1. Counter: <prefix>_requests_total with a `status` label
        counter_re = re.compile(rf'^{re.escape(prefix)}_requests_total\{{[^}}]*status="\d+"', re.MULTILINE)
        assert counter_re.search(body), (
            f"Expected `{prefix}_requests_total{{status=...}}` in /metrics. "
            "SLO availability burn-rate rules will be blind without it."
        )

        # 2. Histogram bucket: <prefix>_request_duration_seconds_bucket{le="0.5"}
        bucket_re = re.compile(rf'^{re.escape(prefix)}_request_duration_seconds_bucket\{{[^}}]*le="0\.5"', re.MULTILINE)
        assert bucket_re.search(body), (
            f'Expected `{prefix}_request_duration_seconds_bucket{{le="0.5"}}` in /metrics. '
            "SLO latency_500ms recording rule depends on it."
        )

        # 3. Histogram count: <prefix>_request_duration_seconds_count
        count_re = re.compile(rf"^{re.escape(prefix)}_request_duration_seconds_count(\{{|\s)", re.MULTILINE)
        assert count_re.search(body), (
            f"Expected `{prefix}_request_duration_seconds_count` in /metrics. "
            "SLO latency_500ms recording rule depends on it."
        )


# ---------------------------------------------------------------------------
# Model metadata `/model/info`
# ---------------------------------------------------------------------------
class TestModelInfoEndpoint:
    def test_model_info_returns_200(self, client: TestClient) -> None:
        response = client.get("/model/info")
        assert response.status_code == 200

    def test_model_info_includes_required_fields(self, client: TestClient) -> None:
        data = client.get("/model/info").json()
        for field in ("model_loaded", "model_type", "version", "model_path"):
            assert field in data

    def test_model_info_reports_loaded(self, client: TestClient) -> None:
        # The conftest mock pre-populates _model_pipeline.
        data = client.get("/model/info").json()
        assert data["model_loaded"] is True


# ---------------------------------------------------------------------------
# Root `/`
# ---------------------------------------------------------------------------
class TestRootEndpoint:
    def test_root_returns_200(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200

    def test_root_links_to_docs(self, client: TestClient) -> None:
        data = client.get("/").json()
        assert data["docs"] == "/docs"
