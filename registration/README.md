# FuzeFront registration

FuzeKeys self-registers with the FuzeFront portal at deploy time.

| File | Purpose |
|---|---|
| `manifest.json` | App identity, Module-Federation contract, `nav` placement |
| `policy.json` | FuzeKeys' own Permit resources/roles, bare keys |
| `register.sh` | Idempotent registration script from `@fuzefront/onboarding-kit` |

## Module Federation contract

Real, and taken from `frontend/vite.config.ts` + `frontend/Dockerfile`:

| Field | Value | Source |
|---|---|---|
| `scope` | `fuzeKeysApp` | federation `name` |
| `module` | `./FuzeKeysApp` | `exposes` key |
| `remoteEntry` | `/apps/fuzekeys/remoteEntry.js` | `base: '/apps/fuzekeys/'`, resolved by the FuzeFront host shell against **its own** origin |

Same-origin, not `https://keys.prod.fuzefront.com/...`: the host shell resolves a
relative `remoteEntry` against `app.fuzefront.com` itself
(`frontend/src/utils/loadFederatedApp.ts:71`, `new URL(remoteEntry, origin)`), and
`deploy/helm/fuzekeys`'s `federatedMount` (enabled in `values-contabo.yaml`, host
`app.fuzefront.com`) proxies `/apps/fuzekeys/*` straight to this frontend Service —
no iframe, no CORS, no mixed-content. An absolute `keys.prod.fuzefront.com` URL is
wrong for the same reason FuzeAgent's was (FuzeFront migration 009): that hostname
sits behind the Cloudflare Access admin wall, which answers an asset request with an
HTML login page instead of JavaScript, so the federation runtime fails with "Failed
to fetch dynamically imported module".

The Dockerfile is explicit about the build layout — `COPY --from=build-mfe /app/dist-mfe
/usr/share/nginx/html/apps/fuzekeys` is commented *"FuzeFront fetches remoteEntry.js
from here"* — and `frontend/nginx.conf` serves that path under BOTH the standalone
`keys.prod.fuzefront.com` host and, via `federatedMount`, `app.fuzefront.com`; only the
latter is reachable by the portal shell.

## Menu placement

```jsonc
"nav": { "section": "platform", "order": 10 }
```

`platform` rather than a lifecycle stage: FuzeKeys is a capability the other apps
consume (its `providesTo` lists 18 repos), not a step in the plan → build → sell → serve
flow.

## Policy — reading a secret is not a read

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
