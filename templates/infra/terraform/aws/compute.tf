# PR-R2-6 (AWS parity) hardening notes:
#  * `endpoint_public_access` is now driven by `var.allow_public_endpoint`
#    and defaults to false — the audit observed a default-public EKS
#    control plane; we close it. Public access, when enabled, is
#    further gated by an explicit CIDR allowlist
#    (`public_endpoint_access_cidrs`), never 0.0.0.0/0.
#  * Cluster KMS envelope encryption for K8s Secrets is enabled with a
#    dedicated key — without this, secrets are encrypted only by EBS
#    at rest, which does not protect against a compromised etcd snap
#    being read in another account.
#  * `enabled_cluster_log_types` ships every relevant control-plane
#    log type into CloudWatch (audit, api, authenticator). Without
#    this, post-incident forensics is essentially impossible.

# Dedicated KMS key for EKS Secrets envelope encryption.
resource "aws_kms_key" "eks_secrets" {
  description             = "${var.project_name}-eks-${var.environment} K8s Secrets envelope encryption (PR-R2-6)"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = {
    environment = var.environment
    managed-by  = "terraform"
    purpose     = "eks-secrets-encryption"
  }
}

resource "aws_kms_alias" "eks_secrets" {
  name          = "alias/${var.project_name}-eks-${var.environment}-secrets"
  target_key_id = aws_kms_key.eks_secrets.key_id
}

# EKS Cluster
resource "aws_eks_cluster" "eks" {
  name     = "${var.project_name}-eks-${var.environment}"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.k8s_version

  # Always-on private endpoint; public is opt-in and CIDR-gated.
  # subnet_ids resolved by network.tf: managed-mode private subnets or
  # caller-provided subnet_ids depending on var.network_mode.
  vpc_config {
    subnet_ids              = local.eks_subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = var.allow_public_endpoint
    public_access_cidrs     = var.allow_public_endpoint ? var.public_endpoint_access_cidrs : []
  }

  # Envelope-encrypt K8s Secrets with our KMS key.
  encryption_config {
    provider {
      key_arn = aws_kms_key.eks_secrets.arn
    }
    resources = ["secrets"]
  }

  # Send every relevant control-plane log type to CloudWatch — required
  # for forensics, retention is configured in logging.tf.
  enabled_cluster_log_types = [
    "api",
    "audit",
    "authenticator",
    "controllerManager",
    "scheduler",
  ]

  # Plan-time guard against the only realistic foot-gun: a caller
  # that flips `allow_public_endpoint=true` but forgets to pass an
  # explicit CIDR allowlist. Without this precondition AWS would
  # accept an empty list silently and behaviour would depend on
  # provider version. Failing here gives an actionable error.
  lifecycle {
    precondition {
      condition     = !(var.allow_public_endpoint && length(var.public_endpoint_access_cidrs) == 0)
      error_message = "When allow_public_endpoint=true, public_endpoint_access_cidrs MUST be a non-empty list of explicit CIDRs (PR-R2-6)."
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy,
    aws_iam_role_policy_attachment.eks_vpc_resource_controller,
  ]
}

# OIDC Provider for IRSA
resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.eks.identity[0].oidc[0].issuer
}

data "tls_certificate" "eks" {
  url = aws_eks_cluster.eks.identity[0].oidc[0].issuer
}

# Node Group
resource "aws_eks_node_group" "nodes" {
  cluster_name    = aws_eks_cluster.eks.name
  node_group_name = "${var.project_name}-nodes"
  node_role_arn   = aws_iam_role.eks_node.arn
  subnet_ids      = local.eks_subnet_ids
  instance_types  = [var.instance_type]

  scaling_config {
    desired_size = var.initial_node_count
    min_size     = var.min_node_count
    max_size     = var.max_node_count
  }

  labels = {
    environment = var.environment
    managed-by  = "terraform"
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.eks_ecr_policy,
  ]
}

# IAM Roles
resource "aws_iam_role" "eks_cluster" {
  name = "${var.project_name}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "eks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role_policy_attachment" "eks_vpc_resource_controller" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role" "eks_node" {
  name = "${var.project_name}-eks-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_node.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_node.name
}

resource "aws_iam_role_policy_attachment" "eks_ecr_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_node.name
}
