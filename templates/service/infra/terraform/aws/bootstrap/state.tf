# ============================================================================
# Terraform state bucket (S3) + lock table (DynamoDB)
# ============================================================================
# Audit High-6 — per-environment state. The live layer's `backend "s3"`
# block in main.tf points at these resources via backend-configs/<env>.hcl.
#
# Why S3 + DynamoDB (not just S3): S3 provides eventual consistency
# guarantees that are insufficient for concurrent terraform applies.
# DynamoDB provides strong consistency for the lock; without it two
# operators can corrupt state.

# ----------------------------------------------------------------------------
# State bucket
# ----------------------------------------------------------------------------
resource "aws_s3_bucket" "tfstate" {
  bucket = "${var.project_name}-tfstate-${var.environment}"

  tags = {
    Name    = "${var.project_name}-tfstate-${var.environment}"
    purpose = "tfstate"
  }

  # Treat as PROTECTED — destroy from this dir would orphan the live state.
  lifecycle {
    prevent_destroy = true
  }
}

# ----------------------------------------------------------------------------
# Access logging for the state bucket
# ----------------------------------------------------------------------------
# Trivy AWS-0089 triage (2026-09-05). The state bucket was versioned,
# KMS-encrypted and public-access-blocked, and nothing recorded WHO read it.
# For a Terraform state file that is the interesting question: state holds
# resource ids, IAM bindings and, historically, anything an operator put in a
# variable. "Who read our state, and when" has no answer without this.
#
# Implemented rather than accepted: the module has no CloudTrail, so there
# was no compensating control to point at — and pointing at one that does not
# exist is the exact failure this repo has now found three times.
resource "aws_s3_bucket" "tfstate_logs" {
  bucket = "${var.project_name}-tfstate-logs-${var.environment}"

  tags = {
    Name    = "${var.project_name}-tfstate-logs-${var.environment}"
    purpose = "tfstate-access-logs"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate_logs" {
  bucket                  = aws_s3_bucket.tfstate_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# The same customer-managed key as the state bucket. AES256 would have been
# simpler and is what most examples show, but Trivy flags it as AWS-0132
# (HIGH): SSE-S3 keys are AWS-owned and unauditable. S3 has supported
# SSE-KMS for server access log delivery since 2023 provided S3 Bucket Keys
# are enabled, which they are below.
#
# Worth recording: adding this bucket to close one LOW finding introduced
# three new ones — including that HIGH — because a new bucket inherits every
# bucket check. Fixing a finding is not free of findings.
resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate_logs" {
  bucket = aws_s3_bucket.tfstate_logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.tfstate.arn
    }
    bucket_key_enabled = true
  }
}

# A separate bucket rather than logging into the state bucket itself:
# self-logging is a feedback loop and AWS rejects it.
resource "aws_s3_bucket_lifecycle_configuration" "tfstate_logs" {
  bucket = aws_s3_bucket.tfstate_logs.id
  rule {
    id     = "expire-access-logs"
    status = "Enabled"
    filter {}
    expiration {
      days = 365
    }
  }
}

resource "aws_s3_bucket_logging" "tfstate" {
  bucket        = aws_s3_bucket.tfstate.id
  target_bucket = aws_s3_bucket.tfstate_logs.id
  target_prefix = "tfstate-access/"
}

# Versioning catches accidental rollback / `terraform state rm`.
resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption with our KMS key (envelope encryption).
resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.tfstate.arn
    }
    bucket_key_enabled = true
  }
}

# Block all public access — state files contain resource IDs that should
# not be enumerable from outside the account.
resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle: archive old non-current versions, delete after retention.
resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.state_bucket_retention_days
    }
  }
}

# ----------------------------------------------------------------------------
# DynamoDB lock table
# ----------------------------------------------------------------------------
# Pay-per-request: state lock acquisitions are infrequent (handful per day),
# so on-demand pricing wins over provisioned capacity for this workload.
resource "aws_dynamodb_table" "tfstate_locks" {
  name         = "${var.project_name}-tfstate-lock-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  # SSE with our KMS key.
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.tfstate.arn
  }

  # Point-in-time recovery enables 35-day rollback if the lock table is
  # deleted or corrupted (e.g. an errant `terraform force-unlock` storm).
  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name    = "${var.project_name}-tfstate-lock-${var.environment}"
    purpose = "tfstate-lock"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# ----------------------------------------------------------------------------
# Outputs — paste into backend-configs/<env>.hcl
# ----------------------------------------------------------------------------
output "tfstate_bucket" {
  description = "S3 bucket for live-layer remote state."
  value       = aws_s3_bucket.tfstate.id
}

output "tfstate_lock_table" {
  description = "DynamoDB table for state locking."
  value       = aws_dynamodb_table.tfstate_locks.name
}

output "tfstate_kms_key_arn" {
  description = "KMS key ARN for envelope encryption."
  value       = aws_kms_key.tfstate.arn
}
