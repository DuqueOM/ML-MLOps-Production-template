# GKE Cluster
#
# Network wiring (ADR-017 / PR-A1):
#   * `network` and `subnetwork` come from `local.*_self_link` defined in
#     network.tf. Whether the VPC was created here (managed mode) or
#     looked up via data source (existing mode) is invisible at this layer.
#   * Secondary ranges for pods + services are referenced by name; the
#     names match what network.tf creates in managed mode and what callers
#     MUST pre-create in their existing subnetwork.
resource "google_container_cluster" "gke" {
  name                     = "${var.project_name}-gke-${var.environment}"
  location                 = var.region
  networking_mode          = "VPC_NATIVE"
  initial_node_count       = 1
  remove_default_node_pool = true

  network    = local.network_self_link
  subnetwork = local.subnetwork_self_link

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  network_policy {
    enabled = true
  }

  # ADR-015 PR-A3 — control-plane reachability.
  # `enable_private_endpoint` defaults true for secure staging/prod
  # posture. Dev environments may explicitly set it false and constrain
  # access with `master_authorized_networks_config`.
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = var.enable_private_endpoint
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # Always emitted, never conditional.
  #
  # This used to be a `dynamic` block gated on the list being non-empty, so
  # with the default empty list the cluster got NO authorized-networks
  # configuration at all — and GKE's default is then "no restriction". That
  # is harmless while `enable_private_endpoint = true` (the default), and it
  # is a publicly reachable control plane the moment an adopter takes the
  # documented dev opt-out and sets it false without also supplying a list.
  #
  # Emitting the block unconditionally inverts the failure mode: an empty
  # list now means "authorized networks enabled, no external CIDR allowed" —
  # the restrictive reading rather than the permissive one. The precondition
  # below makes the dangerous combination impossible outright.
  #
  # It also makes the configuration statically visible. GCP-0061 (and tfsec's
  # google-gke-enable-master-networks before it) fired here because no static
  # analyser evaluates `dynamic` blocks. The finding was suppressed for two
  # releases on the grounds that the HCL was correct anyway; it was not.
  master_authorized_networks_config {
    dynamic "cidr_blocks" {
      for_each = var.master_authorized_networks
      content {
        cidr_block   = cidr_blocks.value.cidr_block
        display_name = cidr_blocks.value.display_name
      }
    }
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = local.pods_range_name
    services_secondary_range_name = local.services_range_name
  }

  release_channel {
    channel = "REGULAR"
  }

  # Trivy GCP-0051. Every bucket, key and service account in this module
  # carries these; the cluster did not, so cost attribution and ownership
  # queries had a hole exactly where the spend is.
  resource_labels = {
    environment = var.environment
    managed-by  = "terraform"
    component   = "gke"
  }

  lifecycle {
    # The invariant the old suppression's justification claimed was "enforced
    # by the variable validation rule in variables.tf". No such rule existed.
    #
    # A public control plane is acceptable only when it is constrained. This
    # is a cross-variable condition, so it cannot live in a `validation`
    # block on either variable — those could not reference other variables
    # until Terraform 1.9, and this module targets >= 1.7. A resource
    # precondition can, and it fails at plan time rather than at apply.
    precondition {
      condition     = var.enable_private_endpoint || length(var.master_authorized_networks) > 0
      error_message = <<-EOT
        enable_private_endpoint = false exposes the GKE control plane on a
        public endpoint, so master_authorized_networks must list the CIDRs
        allowed to reach it. Either keep the private endpoint (the default),
        or supply master_authorized_networks. Leaving both unset would put an
        unrestricted public control plane in front of the cluster.
      EOT
    }
  }
}

# ============================================================================
# Node pools (ADR-015 PR-A3)
# ============================================================================
# Two pools by purpose:
#
#   system   — kube-system, monitoring, ingress controllers, Kyverno
#              (no taint; everything tolerates it)
#   workload — ML service pods (taint: workload-type=ml-services:NoSchedule)
#
# Why split:
#   * Blast radius: an OOM in a workload pod cannot evict kube-dns or the
#     Prometheus stateful set, because those land on system nodes.
#   * Cost: the system pool is small (e2-small, 1-2 nodes); the workload
#     pool autoscales independently with HPA-driven demand.
#   * Upgrades: surge upgrades on the workload pool don't disturb the
#     control-plane add-ons.
#
# ML services MUST set tolerations matching the workload taint:
#   tolerations:
#     - key: workload-type
#       operator: Equal
#       value: ml-services
#       effect: NoSchedule
# ============================================================================

# System pool — small, no taint; runs kube-system + cluster add-ons.
resource "google_container_node_pool" "system" {
  name       = "${var.project_name}-system-pool"
  location   = var.region
  cluster    = google_container_cluster.gke.name
  node_count = var.system_node_count

  autoscaling {
    min_node_count = 1
    max_node_count = 3
  }

  node_config {
    machine_type = var.system_machine_type
    disk_size_gb = 30
    disk_type    = "pd-standard"

    # Dedicated node identity (D-31 / ADR-017). Without it GKE falls back to
    # the DEFAULT Compute Engine service account, which in most projects
    # carries roles/editor across the whole project — flagged as GCP-0050.
    # Pods do not use this identity; they impersonate runtime/drift/retrain
    # through Workload Identity. It covers node-level operations only.
    service_account = google_service_account.nodes.email

    # Container-Optimized OS with containerd (Trivy GCP-0054). COS is GKE's
    # current default, which is precisely why it is pinned: a default is not
    # a decision, and inheriting it silently means a future change to the
    # default — or an override elsewhere — lands a different node OS with a
    # different attack surface without anyone choosing it.
    image_type = "COS_CONTAINERD"

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    # Disable legacy instance metadata endpoint (tfsec google-gke-metadata-endpoints-disabled).
    # GKE_METADATA mode (above) shields workload credentials via Workload Identity;
    # this attribute additionally blocks the v0.1 legacy endpoint that pre-dates
    # the metadata-flavor header requirement. Key must be quoted — tfsec's HCL
    # parser treats unquoted `disable-legacy-endpoints` as an arithmetic expression.
    metadata = {
      "disable-legacy-endpoints" = "true"
    }

    oauth_scopes = var.node_oauth_scopes

    labels = {
      environment   = var.environment
      managed-by    = "terraform"
      workload-type = "system"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# Workload pool — taint scheduled-only for ML services.
resource "google_container_node_pool" "workload" {
  name       = "${var.project_name}-workload-pool"
  location   = var.region
  cluster    = google_container_cluster.gke.name
  node_count = var.initial_node_count

  autoscaling {
    min_node_count = var.min_node_count
    max_node_count = var.max_node_count
  }

  node_config {
    machine_type = var.machine_type
    disk_size_gb = 50
    disk_type    = "pd-standard"

    # Dedicated node identity (D-31 / ADR-017). Without it GKE falls back to
    # the DEFAULT Compute Engine service account, which in most projects
    # carries roles/editor across the whole project — flagged as GCP-0050.
    # Pods do not use this identity; they impersonate runtime/drift/retrain
    # through Workload Identity. It covers node-level operations only.
    service_account = google_service_account.nodes.email

    # Container-Optimized OS with containerd (Trivy GCP-0054). COS is GKE's
    # current default, which is precisely why it is pinned: a default is not
    # a decision, and inheriting it silently means a future change to the
    # default — or an override elsewhere — lands a different node OS with a
    # different attack surface without anyone choosing it.
    image_type = "COS_CONTAINERD"

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    # Disable legacy instance metadata endpoint (tfsec google-gke-metadata-endpoints-disabled).
    # Key quoted for tfsec HCL parser compatibility (see system pool comment above).
    metadata = {
      "disable-legacy-endpoints" = "true"
    }

    oauth_scopes = var.node_oauth_scopes

    labels = {
      environment   = var.environment
      managed-by    = "terraform"
      workload-type = var.workload_node_taint_value
    }

    # NoSchedule taint — pods without a matching toleration cannot land here.
    # ML service Deployments must add the matching toleration (see PR-A3
    # docs in k8s/base/deployment.yaml).
    taint {
      key    = var.workload_node_taint_key
      value  = var.workload_node_taint_value
      effect = "NO_SCHEDULE"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}
