# Argo CD wiring for FuzeKeys — owned by this repo

`deploy/argocd/` holds FuzeKeys's app-of-apps, its two child Applications, its
`fuzekeys` `AppProject` and its sealed secrets — and this repo owns all of them.
FuzeInfra registers this directory once; ArgoCD self-syncs it thereafter.

## Who owns what — correcting an earlier claim in this file

An earlier revision opened *"FuzeInfra owns Argo `Application` and `AppProject`
objects... this directory therefore must not gain any NEW Application manifest"*,
and described the manifests already here as leftovers *"from before the family
moved Application ownership to FuzeInfra"*, to be deleted by a later workstream.

**That is wrong on both counts.** No such move happened, and these are not
leftovers — they are the wiring, and they stay.

FuzeInfra's own onboarding contract
([`docs/CONSUMER_ONBOARDING_SHARED_CLUSTER.md`](https://github.com/izzywdev/FuzeInfra/blob/main/docs/CONSUMER_ONBOARDING_SHARED_CLUSTER.md)):

> Boundary: the consumer owns its `deploy/**` (Helm/kustomize + Argo Applications
> + sealed secrets). FuzeInfra owns the cluster, Argo, the tunnel, and the shared
> datastores.

Note that the boundary names **sealed secrets** explicitly too — `deploy/argocd/sealed/`
belongs here for the same reason the Applications do.

FuzeInfra's `argocd-register` workflow is built around it: it takes a *"Path in
the consumer repo holding the Argo Application/AppProject manifests"*,
`kubectl apply`s the directory **once**, and then

> After the first registration, ArgoCD polls and self-syncs the consumer's
> `deploy/argocd` manifests.

Registration is a **one-time owner action** — never `kubectl apply` from CI or by
hand from here.

That mistaken claim was propagated to several sibling repos in the same session
and used to delete their Applications outright (FuzeService #32, FuzeSales #44),
leaving them with no path to prod. Those deletions are being reverted.
**FuzeKeys's manifests were never deleted**, so nothing here changes but the
wording.

## The invariant that IS real

**One Application per workload.** FuzeContact #33 and FuzeMarket #61 removed
*duplicates*: two Applications with `prune: true` + `selfHeal: true` on the same
namespace with disagreeing values, each pruning what the other did not create.

FuzeKeys's manifests are **not** that — the app-of-apps recurses into
`applications/`, and each child owns a **different** path:

| Manifest | Deploys |
|---|---|
| `project.yaml` | the `fuzekeys` `AppProject` |
| `app-of-apps.yaml` | recursive discovery of `applications/` |
| `applications/fuzekeys-platform.yaml` | `deploy/helm/fuzekeys` — the product chart |
| `applications/fuzekeys-sealed.yaml` | `deploy/argocd/sealed` — the sealed-secret bundle |

> **These manifests are live wiring. Do not delete them, and do not add a second
> Application for any path already listed above.**

## The spec of the committed Applications

| Field | Value |
|---|---|
| `spec.source.repoURL` | `https://github.com/izzywdev/FuzeKeys.git` |
| `spec.source.targetRevision` | `master` |
| `spec.source.path` | `deploy/helm/fuzekeys` |
| `spec.source.helm.releaseName` | `fuzekeys` |
| `spec.source.helm.valueFiles` | `values-contabo.yaml` (layers on the chart's own `values.yaml`) |
| `spec.destination.server` | `https://kubernetes.default.svc` |
| `spec.destination.namespace` | `fuzekeys` |
| `spec.project` | `fuzekeys` — defined by `project.yaml` in this directory. FuzeInfra's `argocd/projects/` has no `fuzekeys` project, so this repo's is the only one that resolves. |
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
