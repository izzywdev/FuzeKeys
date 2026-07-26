# agent-templates — Managed-Agents role framework (FuzeSDLC L0 canonical)

This is the **canonical, repo-agnostic framework** for projecting the org's persona agents
(`.claude/agents/*.md`) onto a provider's **managed-agents** runtime (Anthropic Claude
Managed Agents today; OpenAI / Hermes are stubs). It is the L0 source of truth: the
`sdlc-bootstrap` skill stamps this tree into every consuming repo, and CI-time
**governance-sync** keeps each repo's copy reconciled to this one.

A role bundles three things so a coding session never stalls asking a human to "run this on
the cluster" or "do this on GitHub":

1. **Persona** — the repo's `.claude/agents/<role>.md` (git source of truth) becomes the agent `system`.
2. **Environment** — a `POST /v1/environments` sandbox with the role's packages + network reach.
3. **Permissions** — per-tool policies (`always_allow` / `always_ask`) + credential scoping (vaults).

## What lives where (the split)

| Layer | Home | Contents |
|---|---|---|
| **Framework / pattern** (this tree) | **FuzeSDLC** (canonical) → stamped per repo | `schema/`, `roles/_base/`, `sync/` (REST client, manifest loader, validate), `providers/` (seam + anthropic ref + openai/hermes stubs + `provision.py`) |
| **Concrete definitions** | **each consuming repo** | `roles/<role>/role.json`, `environments/*.json`, `vaults/*.json`, `memory/*.json`, `coordinator/*.json` — declared in `.fuze/manifest.json` `roles` |
| **Orchestration runtime** | **[FuzeAgent](https://github.com/izzywdev/FuzeAgent)** | the deployed handoff MCP server, `relay.py` (session-resume / memory hand-forward), the self-hosted worker image, and the running sessions — imports this `providers/` package |

> The richest worked example (17 roles, 11 environments, exec + persona + GTM tiers, secured
> handoff MCP on Contabo k3s) lives in **FuzeInfra** — use it as the reference when populating a
> repo's concrete definitions.

## Roles are one-per-role, not per-repo

There is **one `backend` role template**, not `fuzeinfra-backend` + `fuzefront-backend` + …. A
repo is not a different agent — it's a different **environment** bound at launch (toolchain,
checkout, networking, creds) plus its repo-expert. A **session** is one `role × environment`
instantiation; you run many in parallel per feature. So *"fuzefront-backend"* = the Backend
template × the FuzeFront env (+ its vault/skills), assembled at `create_session` (optionally via
`agent_with_overrides`) — not a stored per-repo agent.

## Layout (this framework tree)

| Path | What |
|---|---|
| `providers/` | provider seam: `base.py` interface, registry, `anthropic/` (ref) + `openai`/`hermes` stubs, `provision.py` |
| `schema/` | JSON Schemas for `role.json`, environment, vault, memory, mobile-requirements configs |
| `roles/_base/role.json` | shared guardrail system-prompt, default tools + policies, github + handoff MCP (repo-agnostic) |
| `sync/` | stdlib REST client (`common.py`), manifest loader (`role_loader.py`), `validate.py`, session driver/launcher |

A consuming repo adds `roles/<role>/`, `environments/`, `vaults/`, `memory/`, `coordinator/`
alongside these — see the `managed-agents-roles` skill for the procedure and `_base` for the
inheritance model (`"extends": "_base"`).

## Provisioning (runs in the consuming repo)

```bash
cd agent-templates

# 1. validate every manifest (schema + persona render) before touching the API
python sync/validate.py

# 2. preview the full create-plan offline — no API calls (works even without a valid key)
python providers/provision.py --provider anthropic --dry-run

# 3. create/update EVERYTHING (environments + vaults + memory + agents + coordinators),
#    idempotently; prints every id and writes .state/*.json. Reads ${GITHUB_MCP_URL/TOKEN},
#    ${HANDOFF_MCP_URL}, and a Managed-Agents-entitled ${ANTHROPIC_API_KEY}.
python providers/provision.py --provider anthropic
```

In CI this is driven by the reusable **`provision.yml`** workflow (`uses:
izzywdev/FuzeSDLC/.github/workflows/provision.yml@<ref>`); the per-repo **`provision-sync.yml`**
caller (stamped by `sdlc-bootstrap`) invokes it on merges to `main` that touch a definition, so
agent-definition changes reconcile into their deployed counterparts. `provision.py` only updates
an agent/environment when its config actually changed (a no-op otherwise); it never prunes.

## How this removes the "I don't have access" stall

Access is a property of the **environment**, fixed at definition time — not negotiated
mid-session. Cloud roles hold no cluster/prod credentials; a **devops** role runs on a
**self-hosted worker inside the network** where the kubeconfig, PAT and cloud keys live. A
**coordinator** classifies each request and delegates to the role whose environment already has
the access. Irreversible/prod actions are gated three ways: control-plane `always_ask` approval,
OS-level guard shims on the worker, and a prod-sanity system prompt. Scoped-RBAC on the worker's
ServiceAccount is the primary control; the shims are a backstop.

## Keeping in sync

Each repo's copy of this tree is reconciled to the FuzeSDLC canonical at CI time by
`governance-sync.yml` (and nightly by `governance-nightly.yml`). Update the framework **here**;
consuming repos pick it up on their next PR. Concrete role/env/vault definitions are the repo's
own and are **not** overwritten by sync — only the framework files (`schema/`, `roles/_base/`,
`sync/`, `providers/`) are canonical.

## Notes / to confirm before production

- Environments are **not versioned**; changing an `environments/*.json` config means the adapter
  archives + recreates by name.
- Give any self-hosted worker a **scoped-RBAC** kubeconfig, not cluster-admin — the guard shims
  are defense-in-depth, not the primary boundary.
