# Inputs for the FuzeKeys DNS declaration. Real values are injected AT APPLY by
# FuzeInfra's infra-request handler (from its own Cloudflare secrets) — NEVER
# committed here. Empty/placeholder defaults let `terraform validate` run locally
# without secrets.

variable "cloudflare_dns_token" {
  description = "Cloudflare API token (family-zone DNS:Edit) — injected at apply by FuzeInfra's handler; never committed."
  type        = string
  sensitive   = true
  default     = ""
}

variable "cloudflare_zone_id" {
  description = <<-EOT
    Cloudflare zone ID that owns the prod.fuzefront.com records. A public
    identifier (not a secret), but it is FuzeInfra-owned, so the handler supplies
    the correct value at apply time. Left empty here to avoid committing a wrong
    or stale zone id.
  EOT
  type        = string
  default     = ""
}
