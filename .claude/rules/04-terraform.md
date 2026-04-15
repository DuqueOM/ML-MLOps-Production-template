---
paths:
  - "**/*.tf"
  - "infra/**/*"
---

# Terraform Rules

- ALWAYS use remote state (GCS for GCP, S3+DynamoDB for AWS)
- NEVER commit secrets to tfvars or repository — use Secrets Manager
- NEVER commit terraform.tfstate to git — move to remote state, rotate exposed secrets
- ALWAYS use IRSA (AWS) and Workload Identity (GCP) for pod IAM
