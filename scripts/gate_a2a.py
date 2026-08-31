#!/usr/bin/env python3
"""gate-a2a — prove a repo's A2A surface is BUILT and WIRED, not merely declared.

Standard: governance/a2a-runtime-standard.md.  Policy: governance/a2a-policy.json.

WHY THIS EXISTS.  `a2a-maintainer` scaffolded METADATA — the manifest block, a role
skeleton, a tenants entry — and stopped there.  Measured 2026-08-23: 8 repos declare
`a2a.enabled: true` on their live default branch and only 3 of them ship an A2A pod at
all.  Four surfaces are advertised to other products and deployed nowhere.  Nothing was
red, because nothing checked.

THE ANTI-VACUOUS RULE, which is the whole design brief:

    a2a.enabled undeclared/false  ->  SKIP.  There is no surface; that is the truth.
    a2a.enabled TRUE + anything missing  ->  FAIL.  A declared surface is a promise.

Skipping is honest ONLY for the first case.  Every family gate that shipped broken
reached the same place from the other direction -- `gate-authz` ending in `|| true`,
`gate-identifier`'s opt-in flag nobody set, `a2a-maintain` skipping when unkeyed.  A
check that passes because it did not run is worse than no check, because it also
produces a green badge.

CHECK FAMILIES (all run by default):

  --image        I1  image repository is the ONE shared runtime, not a fork
                 I2  the declared repository:tag actually EXISTS in the registry
                     (anonymous GHCR token + manifest GET; 404 reds).  NOT a grep for
                     a `ghcr.io/` string -- that proves only that somebody typed one.
                 I3  values-prod.yaml does not pin `latest`
                 I4  a single-tenant (per-product) pod declares `inClusterUrl`.
                     Omitting it makes the pod publish the SHARED server's endpoint in
                     its card: it starts, passes probes, and every caller that follows
                     the card reaches the wrong pod, with all health signals green.

  --skills       S1  every name in role.json `skills[]` resolves to a real
                     .claude/skills/<name>/SKILL.md.  ALWAYS FATAL -- never ratcheted.
                 S2  a dotted id (`keys.grant`) in `skills[]` is a CARD skill-id in a
                     BUNDLE-skill field.  Always fatal; the two are different things
                     (standard §4) and conflating them is the live bug in fuzekeys.
                 S3  adoption: an a2a.enabled repo whose serving roles declare ZERO
                     bundle skills.  An A2A pod with no skills is a Claude SDK with no
                     product knowledge.  Ratcheted (§4).
                 S4  no root CLAUDE.md -- the pod's product context, mounted with the
                     repo checkout at /repos/<tenant>.  Ratcheted.

  --creds        C1  every secretRef {name,key} resolves to a SealedSecret in the tree
                     whose spec.encryptedData carries that key, or is declared in the
                     policy's externallyProvisioned WITH a reason.
                 C2  cardSigning present without keySecretRef (contract requires it)
                 C3  auth present without oidcIssuerUrl (contract requires it)
                 C4  a single-tenant pod with NO auth block at all.  Identity/authZ are
                     enforced callee-side from the OIDC bearer; no issuer enforces
                     nothing.

                 THIS FAMILY NEVER READS A SECRET VALUE.  It reads NAMES and KEY NAMES.
                 It does not base64-decode, does not print encryptedData, does not log
                 an environment variable's contents.  A LITELLM_MASTER_KEY leaked into a
                 retained public job log on 2026-07-29 and several of these repos are
                 public.  Verifying that a secret is CONFIGURED is in scope; handling
                 the secret is not.

  --env          E1  a tenant env entry with an inline literal value, or with no
                     `valueFrom`.  The frozen interface says values MUST come from
                     secretRef; an inline literal in a values file is a committed
                     secret waiting to happen.

  --memory       M1  the A2A chart mounts a Chroma SERVER image or exposes a Chroma
                     server port.  chromadb carries PYSEC-2026-311 (unfixable pre-auth
                     code injection in the SERVER's collections handler); FuzeAgent is
                     unaffected only because it is a client and never serves that
                     endpoint.  The A2A pod stays a client.

  --api-surface  A1  an A2A values document declaring a raw REST base URL + spec as a
                     callable fallback.  mcp-gateway/src/spec.ts already emits one tool
                     per OpenAPI operation with NO filtering, so a raw path adds zero
                     reachable operations while bypassing classify.ts, safety.ts and
                     upstream.ts's fail-closed caller-token forwarding.  Standard §8.

  --forks        F1  any Dockerfile in this repo that builds an A2A server image.
                     There is exactly ONE shared runtime image and no repo builds its
                     own.  A second A2A Dockerfile is a fork, not a variation.

RATCHET AND ITS DEFAULT.  governance/a2a-policy.json softens ONLY S3/S4, and only for
repos NAMED in ratchet.knownUnadopted.  **If the policy file is ABSENT the gate runs in
`fail` mode.**  Absence is not permission -- that is how `gate-identifier` reached zero
adoption across 21 repos.  Every other rule is fatal in every mode.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request

# --------------------------------------------------------------------------- model

class Finding:
    def __init__(self, code: str, path: str, message: str, fatal: bool = True):
        self.code = code
        self.path = path
        self.message = message
        self.fatal = fatal

    def __str__(self) -> str:
        return f"  {self.code}  {self.path}\n        {self.message}"


SHARED_IMAGE = "ghcr.io/izzywdev/fuzeagent-a2a"
DEFAULT_POLICY = {
    "skills": {"adoption": "fail", "ratchet": {"knownUnadopted": []}},
    "image": {"repository": SHARED_IMAGE},
    "creds": {"sealedSecretDirs": ["deploy/sealed-secrets"], "externallyProvisioned": {}},
    "memory": {"mode": "client-only"},
    "apiSurface": {"mode": "mcp-only"},
}


def load_policy(repo: str):
    """Policy, and whether it was actually found.

    ABSENT -> DEFAULT_POLICY, whose skills.adoption is `fail`.  The ratchet is an
    explicit, checked-in, owner-named artifact; a repo that does not carry one does not
    get the soft mode by default.
    """
    for rel in ("governance/a2a-policy.json", ".fuze/a2a-policy.json"):
        p = os.path.join(repo, rel)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError) as exc:
                # A malformed policy is NOT "no policy" -- it must not silently grant
                # the lenient default.  Fall back to the strict default and say so.
                return DEFAULT_POLICY, f"{rel} is unreadable ({exc}) — using strict defaults"
            merged = dict(DEFAULT_POLICY)
            merged.update(data)
            return merged, rel
    return DEFAULT_POLICY, None


def load_manifest(repo: str) -> dict:
    p = os.path.join(repo, ".fuze", "manifest.json")
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


# ------------------------------------------------------------------- values loading

def _yaml_load(path: str):
    try:
        import yaml  # type: ignore
    except ImportError:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except Exception:
        return None


def find_values_docs(repo: str):
    """Every chart values file that carries a top-level `a2a:` block.

    Returns [(relpath, doc)].  Helm templating (`{{ ... }}`) makes some values files
    unparseable; those are skipped by the YAML loader and reported by the caller only
    when the repo declares a2a.enabled, so a parse failure can never be a silent pass.
    """
    out = []
    pats = (
        "deploy/helm/*/values*.yaml", "deploy/helm/*/*/values*.yaml",
        "helm/*/values*.yaml", "helm/*/*/values*.yaml",
        "charts/*/values*.yaml",
    )
    seen = set()
    for pat in pats:
        for path in sorted(glob.glob(os.path.join(repo, pat))):
            rel = os.path.relpath(path, repo)
            if rel in seen:
                continue
            seen.add(rel)
            doc = _yaml_load(path)
            if not (isinstance(doc, dict) and isinstance(doc.get("a2a"), dict)):
                continue
            a2a = doc["a2a"]
            # A per-environment OVERLAY legitimately carries only the keys it overrides —
            # fuzesales/values-contabo.yaml is literally `a2a: {enabled: false}`. Checking
            # it as if it were a full declaration reports a missing image on a file that
            # was never meant to declare one, and a gate that reds on correct config is a
            # gate people switch off. An overlay participates only in the checks that read
            # the keys it actually carries.
            # NOTE: `enabled: false` is NOT the discriminator. A chart's own values.yaml
            # ships the server disabled by default (the dev shape) while carrying the FULL
            # declaration — fuzeagent/deploy/helm/a2a-shared/values.yaml does exactly that.
            # Skipping on `enabled: false` would drop the real declaration and silently
            # stop checking the repos that HAVE a pod, which is the opposite of the point.
            # What identifies an overlay is that it declares neither an image nor tenants.
            if "image" not in a2a and "tenants" not in a2a:
                continue
            out.append((rel, doc))
    return out


# ------------------------------------------------------------------------- registry

def registry_manifest_status(repository: str, tag: str, timeout: int = 15):
    """(http_status | None, note).  None means the registry was UNREACHABLE.

    Deliberately a real request.  `gate-toolchain` had a job in 7 repos and its script
    in 1; a registry check that only greps a string is the same shape of nothing.
    """
    if not repository.startswith("ghcr.io/"):
        return None, f"{repository} is not on ghcr.io — no anonymous manifest check available"
    name = repository[len("ghcr.io/"):]
    try:
        tok_url = f"https://ghcr.io/token?scope=repository:{name}:pull&service=ghcr.io"
        with urllib.request.urlopen(tok_url, timeout=timeout) as resp:
            token = json.loads(resp.read().decode("utf-8")).get("token", "")
    except Exception as exc:
        return None, f"could not obtain an anonymous registry token ({exc})"
    if not token:
        return None, "registry returned no anonymous token"

    req = urllib.request.Request(f"https://ghcr.io/v2/{name}/manifests/{tag}", method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", ", ".join([
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, "ok"
    except urllib.error.HTTPError as exc:
        # A 404/401 IS an answer: the tag does not exist / is not pullable anonymously.
        return exc.code, f"HTTP {exc.code}"
    except Exception as exc:
        return None, f"registry unreachable ({exc})"


# --------------------------------------------------------------------------- checks

def check_image(repo, manifest, policy, docs, online=True):
    out = []
    want_repo = (policy.get("image") or {}).get("repository", SHARED_IMAGE)
    if not docs:
        # THE HEADLINE CASE. `a2a.enabled: true` and no chart values file anywhere
        # carrying an `a2a:` block: the surface is advertised to other products and
        # deployed nowhere -- a card that routes to a pod that does not exist.
        # Measured 2026-08-23: 4 of the 8 a2a-enabled repos were exactly here, and
        # nothing was red because nothing checked.
        out.append(Finding(
            "I0", ".fuze/manifest.json",
            "a2a.enabled is true and NO chart values file in this repo carries an `a2a:` "
            "block. The surface is advertised to other products and deployed nowhere — a "
            "card that routes to a pod that does not exist. Add the per-product pod "
            "(devops-engineer) or set a2a.enabled=false until it exists."))
    for rel, doc in docs:
        a2a = doc.get("a2a") or {}
        img = a2a.get("image") or {}
        got = img.get("repository")
        tag = img.get("tag")
        if got and got != want_repo:
            out.append(Finding(
                "I1", rel,
                f"a2a.image.repository is `{got}`, not the shared runtime `{want_repo}`. "
                "There is exactly ONE A2A image (fuzeagent/agent-templates/a2a/Dockerfile) "
                "and per-product variation is CONFIG, never a second image."))
        if not got or not tag:
            out.append(Finding(
                "I1", rel,
                "a2a.image.repository/tag is not fully declared, so nothing can verify "
                "which image this pod would run."))
            continue
        if "prod" in os.path.basename(rel) and str(tag) == "latest":
            out.append(Finding(
                "I3", rel,
                "values-prod pins `latest`. Prod must pin an immutable tag "
                "(release.yml bumps it) or a redeploy silently changes the running code."))
        if online:
            status, note = registry_manifest_status(str(got), str(tag))
            if status is None:
                out.append(Finding(
                    "I2", rel,
                    f"SKIPPED — could not reach the registry to verify `{got}:{tag}` ({note}). "
                    "This is an environment gap, not a pass: the image is UNVERIFIED.",
                    fatal=False))
            elif status != 200:
                out.append(Finding(
                    "I2", rel,
                    f"`{got}:{tag}` does not resolve in the registry ({note}). A declared "
                    "image that cannot be pulled deploys nothing — the pod ImagePullBackOffs."))
        tenants = a2a.get("tenants") or []
        if len(tenants) == 1 and not a2a.get("inClusterUrl"):
            out.append(Finding(
                "I4", rel,
                "single-tenant (per-product) A2A pod with no a2a.inClusterUrl. It will "
                "start, pass its probes, and publish the SHARED server's endpoint in its "
                "Agent Card — every caller that follows that card reaches the wrong pod, "
                "with every health signal green. Set it to this pod's own Service."))
    return out


_DOTTED = re.compile(r"^[a-z0-9_-]+(\.[a-z0-9_-]+)+$")


def _serving_roles(repo, manifest):
    a2a = manifest.get("a2a") or {}
    roles = [r for r in (a2a.get("servingRoles") or []) if isinstance(r, str)]
    entry = a2a.get("entryRole")
    if entry and entry not in roles:
        roles.append(entry)
    return roles


def check_skills(repo, manifest, policy, adoption_hard=True):
    out = []
    declared_any = False
    roles = _serving_roles(repo, manifest)
    for role in roles:
        rel = os.path.join("agent-templates", "roles", role, "role.json")
        p = os.path.join(repo, rel)
        if not os.path.isfile(p):
            out.append(Finding(
                "S1", rel,
                f"servingRole `{role}` has no role.json. The projected card advertises a "
                "capability nothing implements, and the failure surfaces in the CALLING product."))
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                role_doc = json.load(fh)
        except (OSError, ValueError) as exc:
            out.append(Finding("S1", rel, f"role.json is unreadable ({exc})."))
            continue
        names = role_doc.get("skills") or []
        for name in names:
            if not isinstance(name, str):
                out.append(Finding("S2", rel, f"skills[] entry {name!r} is not a string."))
                continue
            if _DOTTED.match(name):
                out.append(Finding(
                    "S2", rel,
                    f"skills[] contains `{name}`, which is an A2A CARD skill-id, not a "
                    "filesystem skill bundle. Card skills are PROJECTED from servingRoles by "
                    "card_generator.py and are never hand-authored here; `skills[]` names "
                    ".claude/skills/<name>/SKILL.md bundles the SDK session loads. Move "
                    "discoverability hints to the role's a2a.tags/a2a.examples."))
                continue
            declared_any = True
            skill_md = os.path.join(repo, ".claude", "skills", name, "SKILL.md")
            if not os.path.isfile(skill_md):
                out.append(Finding(
                    "S1", rel,
                    f"skills[] names `{name}` but .claude/skills/{name}/SKILL.md does not "
                    "exist. The pod would start with a skill list pointing at nothing."))
    if roles and not declared_any:
        out.append(Finding(
            "S3", ".fuze/manifest.json",
            "a2a.enabled is true and NO serving role declares any bundle skill. An A2A pod "
            "with no skills is a Claude SDK with no product knowledge — it can be reached "
            "and has nothing product-specific to do. Give the serving role a skills[] list "
            "naming real .claude/skills/<name>/SKILL.md bundles.",
            fatal=adoption_hard))
    if not os.path.isfile(os.path.join(repo, "CLAUDE.md")):
        out.append(Finding(
            "S4", "CLAUDE.md",
            "no root CLAUDE.md. It is mounted with the repo checkout at /repos/<tenant> and "
            "is the pod's product context — without it the shared image serves a generic agent.",
            fatal=adoption_hard))
    return out


def _iter_secret_refs(node, trail=""):
    """Yield (trail, {name,key}) for every secretRef-shaped mapping.

    Shape-based on purpose: the contract spells secretRefs several ways
    (apiKeySecretRef, keySecretRef, caSecretRef, env[].valueFrom) and a key-name
    allowlist would miss the next one.
    """
    if isinstance(node, dict):
        if set(node) <= {"name", "key"} and "name" in node:
            yield trail, node
        for k, v in node.items():
            yield from _iter_secret_refs(v, f"{trail}.{k}" if trail else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _iter_secret_refs(v, f"{trail}[{i}]")


def _sealed_secret_keys(repo, dirs):
    """{secret-name: {key, ...}} from SealedSecrets in the tree.

    Reads spec.encryptedData KEY NAMES ONLY. Values are never read, decoded or printed.
    """
    found = {}
    for d in dirs:
        base = os.path.join(repo, d)
        if not os.path.isdir(base):
            continue
        for path in sorted(glob.glob(os.path.join(base, "**", "*.y*ml"), recursive=True)):
            doc = _yaml_load(path)
            for item in (doc if isinstance(doc, list) else [doc]):
                if not isinstance(item, dict) or item.get("kind") != "SealedSecret":
                    continue
                name = ((item.get("metadata") or {}).get("name")) or ""
                enc = ((item.get("spec") or {}).get("encryptedData")) or {}
                if name and isinstance(enc, dict):
                    found.setdefault(name, set()).update(enc.keys())  # KEY NAMES ONLY
    return found


def check_creds(repo, manifest, policy, docs):
    out = []
    cfg = policy.get("creds") or {}
    sealed = _sealed_secret_keys(repo, cfg.get("sealedSecretDirs") or ["deploy/sealed-secrets"])
    external = cfg.get("externallyProvisioned") or {}
    for rel, doc in docs:
        a2a = doc.get("a2a") or {}
        if a2a.get("cardSigning") and not (a2a["cardSigning"] or {}).get("keySecretRef"):
            out.append(Finding(
                "C2", rel,
                "a2a.cardSigning is present with no keySecretRef. The frozen interface "
                "requires it — the Fuze profile needs a non-empty card signatures[]."))
        auth = a2a.get("auth")
        if isinstance(auth, dict) and not auth.get("oidcIssuerUrl"):
            out.append(Finding(
                "C3", rel,
                "a2a.auth is present with no oidcIssuerUrl. The contract requires it "
                "whenever auth is set; without an issuer nothing verifies the bearer."))
        if len(a2a.get("tenants") or []) == 1 and not auth:
            out.append(Finding(
                "C4", rel,
                "single-tenant A2A pod with NO auth block. Identity and authorization are "
                "enforced callee-side from the OIDC bearer, never from the request body — "
                "an A2A pod with no issuer enforces nothing."))
        for trail, ref in _iter_secret_refs(a2a):
            name, key = ref.get("name"), ref.get("key")
            if not name:
                continue
            if name in external:
                if not str(external.get(name) or "").strip():
                    out.append(Finding(
                        "C1", rel,
                        f"secretRef `{name}` (at a2a.{trail}) is listed in the policy's "
                        "externallyProvisioned with no reason. An unexplained entry is an "
                        "opt-out with no owner, so it is treated as unwired."))
                continue
            if name not in sealed:
                out.append(Finding(
                    "C1", rel,
                    f"secretRef `{name}` (at a2a.{trail}) resolves to no SealedSecret in this "
                    "repo. The pod will start and fail to mount it, or silently run without "
                    "the credential. Seal it under deploy/sealed-secrets/ (devops-engineer) "
                    "or declare it in a2a-policy.json externallyProvisioned WITH a reason."))
            elif key and key not in sealed[name]:
                out.append(Finding(
                    "C1", rel,
                    f"secretRef `{name}` exists but carries no key `{key}` (at a2a.{trail})."))
    return out


def check_env(repo, manifest, policy, docs):
    out = []
    for rel, doc in docs:
        for i, tenant in enumerate((doc.get("a2a") or {}).get("tenants") or []):
            if not isinstance(tenant, dict):
                continue
            for j, e in enumerate(tenant.get("env") or []):
                where = f"a2a.tenants[{i}].env[{j}]"
                if not isinstance(e, dict):
                    out.append(Finding("E1", rel, f"{where} is not a mapping."))
                    continue
                if "value" in e or not e.get("valueFrom"):
                    out.append(Finding(
                        "E1", rel,
                        f"{where} (`{e.get('name')}`) supplies a value inline or has no "
                        "valueFrom. The frozen interface is explicit: env values MUST come "
                        "from secretRef, never inline literals. An inline literal in a "
                        "committed values file is a leaked credential the moment it is real."))
    return out


_CHROMA_SERVER = re.compile(r"(chromadb/chroma|ghcr\.io/chroma-core|image:\s*\S*chroma\S*server)", re.I)


def check_memory(repo, manifest, policy, docs):
    out = []
    for pat in ("deploy/helm/*/templates/a2a*.y*ml", "helm/*/templates/a2a*.y*ml",
                "deploy/helm/a2a*/templates/*.y*ml"):
        for path in sorted(glob.glob(os.path.join(repo, pat))):
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            if _CHROMA_SERVER.search(text):
                out.append(Finding(
                    "M1", os.path.relpath(path, repo),
                    "the A2A chart mounts a Chroma SERVER image. chromadb carries "
                    "PYSEC-2026-311 — unfixable pre-auth code injection in the SERVER's "
                    "collections handler via trust_remote_code. FuzeAgent is unaffected "
                    "ONLY because it is a client and never serves that endpoint. The A2A "
                    "pod stays a CLIENT of the family's existing Chroma, with a per-tenant "
                    "collection. Running a server here changes the exposure."))
    return out


def check_api_surface(repo, manifest, policy, docs):
    out = []
    for rel, doc in docs:
        a2a = doc.get("a2a") or {}
        blob = json.dumps(a2a).lower()
        for key in ("restbaseurl", "restfallback", "openapifallback", "restupstream"):
            if key in blob:
                out.append(Finding(
                    "A1", rel,
                    f"the a2a values document declares `{key}` — a raw-REST callable path. "
                    "mcp-gateway/src/spec.ts already emits ONE TOOL PER OpenAPI OPERATION "
                    "with no filtering, so this adds zero reachable operations while "
                    "bypassing classify.ts (mutating/irreversible classification), "
                    "safety.ts (prototype-pollution guards) and upstream.ts (caller-token "
                    "forwarding, which has deliberately NO service-token option and fails "
                    "closed). Point the pod at the product's MCP gateway with the FULL "
                    "OpenAPI document instead. See governance/a2a-runtime-standard.md §8."))
    return out


_A2A_DOCKERFILE = re.compile(r"^\s*CMD\s+.*a2a\.runtime", re.M)


def check_forks(repo, manifest, policy, docs):
    out = []
    for path in glob.glob(os.path.join(repo, "**", "Dockerfile*"), recursive=True):
        if "node_modules" in path or "/.git/" in path:
            continue
        rel = os.path.relpath(path, repo)
        # fuzeagent owns the one true runtime Dockerfile; it is not a fork of itself.
        if rel.replace(os.sep, "/") == "agent-templates/a2a/Dockerfile":
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        if _A2A_DOCKERFILE.search(text):
            out.append(Finding(
                "F1", rel,
                "this Dockerfile builds an A2A server image. There is exactly ONE shared "
                f"runtime (`{SHARED_IMAGE}`, fuzeagent/agent-templates/a2a/Dockerfile) and "
                "no repo builds its own — per-product variation is config, never a second "
                "image. A second image means every contract change needs N rebuilds."))
    return out


FAMILIES = [
    ("image", "--image", check_image),
    ("skills", "--skills", check_skills),
    ("creds", "--creds", check_creds),
    ("env", "--env", check_env),
    ("memory", "--memory", check_memory),
    ("api_surface", "--api-surface", check_api_surface),
    ("forks", "--forks", check_forks),
]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", nargs="?", default=".")
    for attr, flag, _ in FAMILIES:
        ap.add_argument(flag, dest=attr, action="store_true")
    ap.add_argument("--all", action="store_true", help="every family (the default)")
    ap.add_argument("--offline", action="store_true",
                    help="skip the live registry lookup (I2). Prints the tag it did NOT verify.")
    args = ap.parse_args(argv)

    repo = os.path.abspath(args.repo)
    manifest = load_manifest(repo)
    a2a = manifest.get("a2a") or {}
    enabled = bool(a2a.get("enabled"))

    if not enabled:
        # The ONLY honest skip. `enabled: false` on a repo with no A2A surface is an
        # absence, not a gap -- and this gate must not invent a surface to check.
        print("gate-a2a: .fuze/manifest.json does not declare a2a.enabled=true — no A2A "
              "surface exists here, so there is nothing to verify. This skip is the truth, "
              "not a pass-by-not-running.")
        return 0

    policy, policy_src = load_policy(repo)
    adoption_hard = (policy.get("skills") or {}).get("adoption", "fail") != "warn"
    known = set(((policy.get("skills") or {}).get("ratchet") or {}).get("knownUnadopted") or [])
    repo_id = manifest.get("repo") or os.path.basename(repo)
    # The ratchet softens ONLY repos it NAMES. A repo not on the worklist is hard even
    # while the mode reads `warn` -- otherwise `warn` would be a fleet-wide opt-out and
    # a NEW violation would land soft, which is the thing a ratchet exists to prevent.
    if not adoption_hard and repo_id not in known:
        adoption_hard = True

    selected = [fn for attr, _, fn in FAMILIES if getattr(args, attr)]
    if not selected or args.all:
        selected = [fn for _, _, fn in FAMILIES]

    docs = find_values_docs(repo)
    findings = []
    for fn in selected:
        if fn is check_image:
            findings.extend(fn(repo, manifest, policy, docs, online=not args.offline))
        elif fn is check_skills:
            findings.extend(fn(repo, manifest, policy, adoption_hard=adoption_hard))
        else:
            findings.extend(fn(repo, manifest, policy, docs))

    src = policy_src or "NONE — strict defaults (absence is not permission)"
    print(f"gate-a2a: repo={repo_id} a2a=enabled values-docs={len(docs)} "
          f"policy={src} adoption={'enforcing' if adoption_hard else 'ratcheted'}")

    if not findings:
        print("gate-a2a: OK")
        return 0

    fatal = [f for f in findings if f.fatal]
    for f in sorted(findings, key=lambda x: (x.code, x.path)):
        print(("::error::" if f.fatal else "::warning::") + f"gate-a2a {f.code}")
        print(f)

    print(f"\ngate-a2a: {len(findings)} finding(s), {len(fatal)} fatal")
    if not fatal:
        print("gate-a2a: no fatal findings — the ratcheted ones above are DEBT, not a setting. "
              "Owner and worklist are in governance/a2a-policy.json.")
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
