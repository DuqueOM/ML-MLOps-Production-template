# Model artifacts bucket
resource "google_storage_bucket" "models" {
  # Customer-managed encryption (Trivy GCP-0066). The key, its rotation and
  # the GCS service agent grant live in kms.tf.
  encryption {
    default_kms_key_name = google_kms_crypto_key.storage.id
  }

  name          = "${var.project_name}-models-${var.environment}"
  location      = var.region
  force_destroy = false

  versioning {
    enabled = true
  }

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle_rule {
    condition {
      age = var.model_archive_days
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = var.model_delete_days
    }
    action {
      type = "Delete"
    }
  }

  logging {
    log_bucket = google_storage_bucket.logs.name
  }
}

# Data bucket
resource "google_storage_bucket" "data" {
  # Customer-managed encryption (Trivy GCP-0066). The key, its rotation and
  # the GCS service agent grant live in kms.tf.
  encryption {
    default_kms_key_name = google_kms_crypto_key.storage.id
  }

  name          = "${var.project_name}-data-${var.environment}"
  location      = var.region
  force_destroy = false

  versioning {
    enabled = true
  }

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
}

# MLflow artifacts bucket
resource "google_storage_bucket" "mlflow_artifacts" {
  # Customer-managed encryption (Trivy GCP-0066). The key, its rotation and
  # the GCS service agent grant live in kms.tf.
  encryption {
    default_kms_key_name = google_kms_crypto_key.storage.id
  }

  name          = "${var.project_name}-mlflow-artifacts-${var.environment}"
  location      = var.region
  force_destroy = false

  versioning {
    enabled = true
  }

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
}

# Access logs bucket
resource "google_storage_bucket" "logs" {
  # Customer-managed encryption (Trivy GCP-0066). The key, its rotation and
  # the GCS service agent grant live in kms.tf.
  encryption {
    default_kms_key_name = google_kms_crypto_key.storage.id
  }

  name          = "${var.project_name}-access-logs-${var.environment}"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }
}

# Artifact Registry
resource "google_artifact_registry_repository" "ml_images" {
  location      = var.region
  repository_id = "${var.project_name}-images"
  format        = "DOCKER"

  labels = {
    environment = var.environment
  }
}
