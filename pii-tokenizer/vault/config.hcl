# Persistent Vault config (replaces dev mode). Data survives container restarts and
# host reboots via the pii-vault-data volume mounted at /vault/file.
storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

disable_mlock = true
ui            = false
api_addr      = "http://127.0.0.1:8200"
