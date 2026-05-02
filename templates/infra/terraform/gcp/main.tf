terraform {
  required_version = ">= 1.7"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.30"
    }
  }

  # Per-environment state segregation (audit High-6).
  # Backend left intentionally empty (partial config) so each environment
  # MUST pass `bucket` + `prefix` at init time:
  #
  #   terraform init -backend-config=backend-configs/dev.hcl
  #   terraform init -backend-config=backend-configs/staging.hcl -reconfigure
  #   terraform init -backend-config=backend-configs/prod.hcl    -reconfigure
  #
  # Backend config files in backend-configs/ pin one bucket+prefix per env
  # so a `terraform apply` in dev cannot mutate prod state. The `-reconfigure`
  # flag is needed when switching between configs in the same .terraform/.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}
