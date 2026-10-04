# Shared Google credential custody

Google Gmail, Drive, Calendar, Contacts, Sheets, Docs, Slides and Tasks share one
OAuth credential per delegated FuzeFront subject. The canonical vault key keeps
the deployed Gmail spelling: `connectors/{encoded-owner}/google-gmail`. Each
provider retains its own database metadata, configuration and connection status.
Other providers remain isolated by both owner and provider.

## Trusted service contract

Shared Google credential PUTs require `google_identity: {subject, client_id}` alongside
`credential`. The consuming service must derive `subject` from Google's verified
HTTPS OpenID userinfo response and `client_id` from the configured OAuth client
that exchanged the code. These values must never come from a browser request or
an email lookup. The delegated service authentication remains required.

The vault stores the credential and binding together; no tokens enter Postgres.
Credential leases return the binding as `google_identity` alongside `credential`.
Refresh uses the consuming service's configured OAuth client, verifies the same
Google identity and supplies the binding on its PUT. An omitted refresh token is
preserved only when the stored and incoming subject/client bindings match.

The actual `credential.scope` grant must cover all connected Google providers on
update, and a lease checks the server-owned resource scopes for its provider.
Old grants are never unioned into a newly issued token to pretend it has consent.
Google mutations and leases acquire a PostgreSQL transaction advisory lock keyed
by the delegated owner, serializing canonical custody across backend replicas.

Disconnect removes the selected provider's metadata. The shared vault credential
is deleted only after its last referencing Google connector disconnects.

## Existing connections and rollout

Legacy Gmail secrets have no verified subject/client binding. They remain readable
at the custody endpoint, but the updated consuming runtime requires reauthorization
before use. A fresh offline-consent refresh token and a verified identity are
required to bind the existing canonical secret; old unverified refresh tokens are
never silently retained.

Only an explicit Gmail reconnect can replace a sole unbound legacy Gmail record.
Connecting another Google provider first returns HTTP 409 even if the incoming
token grants both providers' scopes: scopes cannot prove continuity with the old
Google account. Reauthorize Gmail first, or disconnect the legacy connections.
Multiple unbound Google records must be disconnected before establishing the
verified shared account.

Separate legacy Google vault keys are not automatically combined: they may belong
to different accounts or OAuth clients. PUT returns HTTP 409 until the owner
disconnects those legacy providers and authorizes the intended shared account.
Changing an established Google account or OAuth client similarly requires
disconnecting the existing Google connectors first.

Deploy FuzeKeys first, then the matching FuzeFront runtime. During that window,
an older runtime may still read and overwrite a sole unbound Gmail credential
without an identity envelope. This narrow compatibility path stores the old
opaque blob, never merges an unverified refresh token, cannot enable another
Google provider, and rejects writes once a verified canonical binding exists.
The updated FuzeFront runtime requires verified owner reauthorization before use.
No database schema migration is required:
new metadata rows simply reference the shared canonical key.
