# ============================================================================
# Network topology (ADR-017 / PR-A1)
# ============================================================================
# Two modes:
#
#   network_mode = "managed"   → template creates VPC + 3 private + 3 public
#                                subnets + NAT gateways across 3 AZs
#   network_mode = "existing"  → caller provides subnet_ids (current default)
#
# Local `eks_subnet_ids` exposes the subnet list to compute.tf regardless of
# mode. Existing mode is the default to preserve backwards compatibility.
# ============================================================================

# ---------------------------------------------------------------------------
# Managed mode resources — created only when network_mode == "managed"
# ---------------------------------------------------------------------------

resource "aws_vpc" "managed" {
  count = var.network_mode == "managed" ? 1 : 0

  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "${var.project_name}-vpc-${var.environment}"
    environment = var.environment
    managed-by  = "terraform"
  }
}

# Internet gateway for public subnets (NAT egress)
resource "aws_internet_gateway" "managed" {
  count = var.network_mode == "managed" ? 1 : 0

  vpc_id = aws_vpc.managed[0].id

  tags = {
    Name        = "${var.project_name}-igw-${var.environment}"
    environment = var.environment
    managed-by  = "terraform"
  }
}

# Private subnets (3 AZs) — EKS nodes live here
resource "aws_subnet" "private" {
  count = var.network_mode == "managed" ? length(var.availability_zones) : 0

  vpc_id            = aws_vpc.managed[0].id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 1)
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name                              = "${var.project_name}-private-${count.index + 1}-${var.environment}"
    environment                       = var.environment
    managed-by                        = "terraform"
    "kubernetes.io/role/internal-elb" = "1"
  }
}

# Public subnets (3 AZs) — NAT gateways + LBs live here
resource "aws_subnet" "public" {
  count = var.network_mode == "managed" ? length(var.availability_zones) : 0

  vpc_id                  = aws_vpc.managed[0].id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index + 101)
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false # explicit, do not auto-assign public IPs

  tags = {
    Name                     = "${var.project_name}-public-${count.index + 1}-${var.environment}"
    environment              = var.environment
    managed-by               = "terraform"
    "kubernetes.io/role/elb" = "1"
  }
}

# Elastic IPs for NAT (1 per AZ for HA)
resource "aws_eip" "nat" {
  count = var.network_mode == "managed" ? length(var.availability_zones) : 0

  domain = "vpc"

  tags = {
    Name        = "${var.project_name}-nat-eip-${count.index + 1}-${var.environment}"
    environment = var.environment
    managed-by  = "terraform"
  }

  depends_on = [aws_internet_gateway.managed]
}

resource "aws_nat_gateway" "managed" {
  count = var.network_mode == "managed" ? length(var.availability_zones) : 0

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name        = "${var.project_name}-nat-${count.index + 1}-${var.environment}"
    environment = var.environment
    managed-by  = "terraform"
  }

  depends_on = [aws_internet_gateway.managed]
}

# Route tables — public goes to IGW, private goes to NAT
resource "aws_route_table" "public" {
  count = var.network_mode == "managed" ? 1 : 0

  vpc_id = aws_vpc.managed[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.managed[0].id
  }

  tags = {
    Name        = "${var.project_name}-public-rt-${var.environment}"
    environment = var.environment
    managed-by  = "terraform"
  }
}

resource "aws_route_table" "private" {
  count = var.network_mode == "managed" ? length(var.availability_zones) : 0

  vpc_id = aws_vpc.managed[0].id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.managed[count.index].id
  }

  tags = {
    Name        = "${var.project_name}-private-rt-${count.index + 1}-${var.environment}"
    environment = var.environment
    managed-by  = "terraform"
  }
}

resource "aws_route_table_association" "public" {
  count = var.network_mode == "managed" ? length(var.availability_zones) : 0

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}

resource "aws_route_table_association" "private" {
  count = var.network_mode == "managed" ? length(var.availability_zones) : 0

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# ---------------------------------------------------------------------------
# Locals — single source of truth for compute.tf
# ---------------------------------------------------------------------------
locals {
  eks_subnet_ids = (
    var.network_mode == "managed"
    ? aws_subnet.private[*].id
    : var.subnet_ids
  )
}

# ---------------------------------------------------------------------------
# Plan-time guard: existing mode requires non-empty subnet_ids
# ---------------------------------------------------------------------------
# Implemented as a check block so the error fires at plan time with a
# clear message rather than as a confusing "subnet_ids[0] is null" later.
check "existing_mode_requires_subnet_ids" {
  assert {
    condition     = var.network_mode != "existing" || length(var.subnet_ids) > 0
    error_message = "network_mode='existing' requires var.subnet_ids to be a non-empty list"
  }
}
