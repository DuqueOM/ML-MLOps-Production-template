terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.43"
    }
  }

  # Per-environment state segregation (audit High-6).
  # Backend left intentionally empty (partial config) so each environment
  # MUST pass bucket + key + region + dynamodb_table at init time:
  #
  #   terraform init -backend-config=backend-configs/dev.hcl
  #   terraform init -backend-config=backend-configs/staging.hcl -reconfigure
  #   terraform init -backend-config=backend-configs/prod.hcl    -reconfigure
  #
  # Backend config files in backend-configs/ pin one bucket+key per env so
  # a `terraform apply` in dev cannot mutate prod state.
  backend "s3" {}
}

provider "aws" {
  region = var.region
}
