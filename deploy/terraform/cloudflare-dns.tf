# FuzeKeys public DNS — DECLARED here, APPLIED by FuzeInfra's handler.
#
# FuzeKeys runs on the EXISTING shared Contabo k3s cluster (co-located with
# FuzeInfra), so there is NO node-request here — only the product's DNS. Each
# host is a PROXIED CNAME to the shared FuzeInfra Cloudflare Tunnel entrypoint
# (prod.fuzefront.com). CF terminates TLS at the edge; the tunnel forwards to
# Traefik, which host-routes by Ingress (see deploy/helm/fuzekeys ingress hosts).
#
# The generic cloudflare-dns module and the Cloudflare API token live in
# FuzeInfra; only the product-specific data (zone/hosts) lives here. This is
# applied over the FuzeInfra infra-request dispatch path (shared TF state, no
# consumer secrets, no consumer state backend) — never from this repo directly.
#
# Additive subdomains only — the apex (fuzefront.com) and prod.fuzefront.com
# tunnel record are managed by FuzeInfra and MUST NOT be listed here.
#
#   keys.prod.fuzefront.com      -> frontend  (helm ingress: keys.prod.fuzefront.com)
#   api.keys.prod.fuzefront.com  -> backend   (helm ingress: api.keys.prod.fuzefront.com)

provider "cloudflare" {
  api_token = var.cloudflare_dns_token
}

module "fuzekeys_dns" {
  source          = "git::https://github.com/izzywdev/FuzeInfra.git//modules/cloudflare-dns?ref=main"
  domain          = "prod.fuzefront.com"
  zone_id         = var.cloudflare_zone_id
  tunnel_hostname = "prod.fuzefront.com"
  hosts           = ["keys", "api.keys"]
}
