# Persistent OpenBao config. Data survives restarts/reboots via the idv-openbao-data
# volume mounted at /openbao/file. OpenBao is API-compatible with HashiCorp Vault, so
# the broker and stack-up.sh use the same /v1/sys/* and KV v2 endpoints.
#
# This whole directory is bind-mounted to /openbao/config (the image auto-loads
# `-config=/openbao/config`). Keep ONLY config here — the gitignored unseal-key file
# lives in the parent (openbao/.openbao-init.json), NOT in this dir.
storage "file" {
  path = "/openbao/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

disable_mlock = true
ui            = true
api_addr      = "http://127.0.0.1:8200"
