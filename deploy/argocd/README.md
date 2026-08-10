# Argo CD adoption spec — FuzeKeys

**FuzeInfra owns Argo `Application` and `AppProject` objects.** They are the
destination and security boundary for the shared cluster, so a product repo that
ships its own competes with that boundary. This directory therefore must not gain
any NEW Application manifest, and the spec below — not a YAML file here — is how
FuzeInfra adopts changes to this release.

> **Pre-existing, and NOT changed by this PR.** `applications/fuzekeys-platform.yaml`,
> `applications/fuzekeys-sealed.yaml`, `app-of-apps.yaml` and `project.yaml` are
> still in this repo from before the family moved Application ownership to
> FuzeInfra (FuzeMarket PR #61 did that move for FuzeMarket). Deleting them is a
> deploy-affecting change owned by that workstream, not by this one, so they are
> flagged here rather than removed. When they go, this document is what replaces
> them.

## The spec FuzeInfra needs

| Field | Value |
|---|---|
| `spec.source.repoURL` | `https://github.com/izzywdev/FuzeKeys.git` |
| `spec.source.targetRevision` | `master` |
| `spec.source.path` | `deploy/helm/fuzekeys` |
| `spec.source.helm.releaseName` | `fuzekeys` |
| `spec.source.helm.valueFiles` | `values-contabo.yaml` (layers on the chart's own `values.yaml`) |
| `spec.destination.server` | `https://kubernetes.default.svc` |
| `spec.destination.namespace` | `fuzekeys` |
| `spec.project` | FuzeInfra's decision |
| `spec.syncPolicy.automated` | `prune: true`, `selfHeal: true` |
| `spec.syncPolicy.syncOptions` | `CreateNamespace=true`, `ServerSideApply=true` |

`ServerSideApply=true` matters here: the chart mounts a ~110 KB OpenAPI document
into a ConfigMap, which exceeds what client-side apply can carry in the
`last-applied-configuration` annotation.

## What the release contains

| Workload | Enabled by | Notes |
|---|---|---|
| `fuzekeys-backend` (Deployment + Service, :8002) | `backend.enabled` — **true** | FastAPI. Serves `GET /health` and publishes its own OpenAPI at `/openapi.json` and `/docs`. |
| `fuzekeys-frontend` (Deployment + Service) | `frontend.enabled` — **true** | React SPA on nginx |
| `fuzekeys-migrate` (Job) | `migrate.enabled` | `alembic upgrade head`, pre-sync |
| `fuzekeys-mcp` (Deployment + Service, :8081) | `mcp.enabled` — **true** in `values-contabo.yaml` | the shared `@fuzefront/mcp-gateway` image, pointed at `fuzekeys-backend:8002` |
| `fuzekeys-a2a` (Deployment + Service) | `a2a.enabled` — **false**, everywhere | blocked; preconditions are in `deploy/helm/fuzekeys/templates/a2a.yaml` |
| pii-tokenizer stack (tokenizer, presidio, litellm, vault, ollama, redis) | all **false** in `values-contabo.yaml` | gated off pending the Vault auto-unseal design |

The backend IS deployed, so the MCP pod has a real upstream to call. (That is
worth stating explicitly: a sibling in this family ships a chart that deploys
only its MFE, which leaves its MCP pod able to enumerate tools and unable to
execute any of them.)

## Secrets it expects to already exist in the namespace

| Secret | Provided by | Used for |
|---|---|---|
| `fuzekeys-secrets` (`secrets.existingSecret`) | `deploy/argocd/sealed/fuzekeys-secrets.yaml` | DB URL, encryption keys, API keys |
| `fuzekeys-tokenizer-secrets` | `deploy/argocd/sealed/` | only when the tokenizer stack is enabled |
| `ghcr-pull-secret` | `deploy/argocd/sealed/` | image pulls |

The MCP gateway pod needs **no** Secret — it holds no credential of its own and
forwards the caller's `Authorization` header, which on a credential vault is the
entire point.
