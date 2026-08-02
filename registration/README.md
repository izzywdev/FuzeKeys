# FuzeFront registration

FuzeKeys self-registers with the FuzeFront portal at deploy time.

| File | Purpose |
|---|---|
| `manifest.json` | App identity, Module-Federation contract, `nav` placement |
| `policy.json` | FuzeKeys' own resources/roles, BARE keys — no engine-specific identifiers |
| `register.sh` | Idempotent registration script from `@fuzefront/onboarding-kit` |

## Module Federation contract

Real, and taken from `frontend/vite.config.ts` + `frontend/Dockerfile`:

| Field | Value | Source |
|---|---|---|
| `scope` | `fuzeKeysApp` | federation `name` |
| `module` | `./FuzeKeysApp` | `exposes` key |
| `remoteEntry` | `https://keys.prod.fuzefront.com/apps/fuzekeys/remoteEntry.js` | `base: '/apps/fuzekeys/'` + the `keys.prod.fuzefront.com` ingress host |

The Dockerfile is explicit about this — `COPY --from=build-mfe /app/dist-mfe
/usr/share/nginx/html/apps/fuzekeys` is commented *"FuzeFront fetches remoteEntry.js
from here"* — and `frontend/nginx.conf` serves that path.

## Menu placement

```jsonc
"nav": { "section": "platform", "order": 10 }
```

`platform` rather than a lifecycle stage: FuzeKeys is a capability the other apps
consume (its `providesTo` lists 18 repos), not a step in the plan → build → sell → serve
flow.

## Policy — reading a secret is not a read

These keys are consumed by FuzeFront's authorization API
(`POST /v1/security/authz/check`, `resource: { type }` + `action`). They are
deliberately BARE — FuzeKeys names a resource and an action and nothing else.
Which policy engine evaluates them is FuzeFront's private implementation detail
and never appears in this repo.

Derived from `backend/app/models/`: `Identity`, `Account`, `VaultAsset` (the
`identity_cards` + `api_credentials` tables), `Site`, `SignupScript`, `ApiKey`.

The important split is on `VaultAsset`:

| Action | Meaning |
|---|---|
| `read` | List/inspect **metadata** — which credentials exist, for which site |
| `reveal` | Return the **decrypted secret value** |

`reveal` is granted to **`admin` only**. `operator` can create and rotate credentials
without ever being able to read back an existing one, which is the property that makes
an operator role safe to hand out. Modelling "reveal" as ordinary `read` would have
silently given every viewer the vault contents.

`SignupScript:run` is likewise separated from writes — it drives real account creation
against third-party sites.

## NOT DONE — init container not wired

`deploy/helm/fuzekeys/` is a multi-service chart (backend, frontend, vault, tokenizer,
presidio, litellm). Exactly one deployment must run registration; wiring more than one
would have them race and duplicate-register. `frontend` is the natural owner since it
serves the remote, but confirming that is `devops-engineer`'s call and is flagged rather
than guessed.

To finish: paste the init container from
[`@fuzefront/onboarding-kit`](https://github.com/izzywdev/FuzeFront/blob/master/packages/onboarding-kit/helm/initcontainer.yaml)
into that one pod spec, plus the `fuzefront-registration` Secret and a ConfigMap of this
directory.
