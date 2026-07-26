"""
Attenuable capability handles via **macaroons** (pymacaroons, maintained).

A macaroon is the opaque grant handle. It carries first-party caveats that the
broker verifies on redeem; because each caveat extends the HMAC chain, a holder
can only **add** caveats (NARROW scope/TTL) — never remove one or widen. This is
exactly the multi-hop delegation property we need for A -> B -> C: each hop
attenuates, none can amplify.

We do NOT hand-roll the crypto — pymacaroons implements Google's macaroon
construction (Birgisson, Politz, Erlingsson, Taly, Vrable, Lentczner, 2014,
"Macaroons: Cookies with Contextual Caveats for Decentralized Authorization").

Caveats we mint (predicate form ``key = value`` / ``key <op> value``):
  - ``grant = <grant_id>``          binds the handle to its DB row
  - ``redeemer = <principal>``      only this transport identity may redeem
  - ``expires <= <iso8601>``        TTL ceiling (attenuatable downward)
  - ``scope <= <json>``             capability scope ceiling (attenuatable)
  - ``single_use = true|false``

The root key lives server-side (Grant.root_key). The handle reveals its caveats
(which are policy, not secrets) but never any secret material.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from pymacaroons import Macaroon, Verifier

# Stable identifier for the broker as macaroon "location".
LOCATION = "fuzekeys-broker"


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def mint_handle(
    *,
    root_key: bytes,
    grant_id: str,
    redeemer: str,
    expires_at: datetime,
    scope: dict,
    single_use: bool,
) -> str:
    """Create the serialized macaroon handle for a fresh grant."""
    m = Macaroon(location=LOCATION, identifier=grant_id, key=root_key)
    m.add_first_party_caveat(f"grant = {grant_id}")
    m.add_first_party_caveat(f"redeemer = {redeemer}")
    m.add_first_party_caveat(f"expires <= {expires_at.astimezone(timezone.utc).isoformat()}")
    m.add_first_party_caveat(f"scope <= {json.dumps(scope, sort_keys=True, separators=(',', ':'))}")
    m.add_first_party_caveat(f"single_use = {'true' if single_use else 'false'}")
    return m.serialize()


def attenuate(handle: str, *, caveat: str) -> str:
    """Return a NARROWER handle by appending a first-party caveat.

    The caller cannot remove existing caveats or forge the signature, so this can
    only tighten authority. Used by an intermediary hop (B) delegating to C.
    """
    m = Macaroon.deserialize(handle)
    m.add_first_party_caveat(caveat)
    return m.serialize()


class _Bounds:
    """Collects the tightest ceilings asserted across all caveats."""

    def __init__(self) -> None:
        self.grant: Optional[str] = None
        self.redeemer: Optional[str] = None
        self.expires_at: Optional[datetime] = None
        self.scope: Optional[dict] = None
        self.single_use: Optional[bool] = None


def verify_handle(
    *,
    handle: str,
    root_key: bytes,
    grant_id: str,
    caller: str,
    now: Optional[datetime] = None,
) -> _Bounds:
    """Verify signature + all caveats and return the effective (narrowed) bounds.

    Raises ``ValueError`` on ANY failure (bad signature, wrong grant, wrong
    redeemer, expired, unsatisfiable caveat). The broker converts that into a
    non-disclosing ``BrokerDenied`` — this layer just says yes/no + bounds.
    """
    now = now or datetime.now(timezone.utc)
    bounds = _Bounds()

    def satisfy(predicate: str) -> bool:
        # First-party caveat verifier. Returns True if this caller satisfies the
        # predicate; also records the tightest ceiling for the broker.
        try:
            if predicate.startswith("grant = "):
                val = predicate[len("grant = "):]
                bounds.grant = val
                return val == grant_id
            if predicate.startswith("redeemer = "):
                val = predicate[len("redeemer = "):]
                bounds.redeemer = val
                return val == caller
            if predicate.startswith("expires <= "):
                val = _parse_iso(predicate[len("expires <= "):])
                if bounds.expires_at is None or val < bounds.expires_at:
                    bounds.expires_at = val
                return now <= val
            if predicate.startswith("scope <= "):
                val = json.loads(predicate[len("scope <= "):])
                bounds.scope = _narrow_scope(bounds.scope, val)
                return True  # scope containment is enforced by the broker vs request
            if predicate.startswith("single_use = "):
                val = predicate[len("single_use = "):].strip() == "true"
                # single_use can only be tightened false->true
                if bounds.single_use is None:
                    bounds.single_use = val
                else:
                    bounds.single_use = bounds.single_use or val
                return True
        except Exception:
            return False
        return False

    m = Macaroon.deserialize(handle)
    v = Verifier()
    v.satisfy_general(satisfy)
    # pymacaroons raises MacaroonInvalidSignatureException / MacaroonUnmetCaveat...
    # on any failure (bad sig, unsatisfiable caveat). Normalize ALL of these into
    # a single ValueError so the broker can map it to a non-disclosing denial.
    try:
        ok = v.verify(m, root_key)
    except Exception as exc:  # noqa: BLE001 - intentional: collapse to one signal
        raise ValueError(f"macaroon verification failed: {type(exc).__name__}")
    if not ok:
        raise ValueError("macaroon verification failed")
    if bounds.grant != grant_id:
        raise ValueError("grant caveat missing/mismatch")
    if bounds.redeemer != caller:
        raise ValueError("redeemer caveat missing/mismatch")
    return bounds


def _narrow_scope(current: Optional[dict], incoming: dict) -> dict:
    """Intersect two scope dicts (attenuation = intersection, never union)."""
    if current is None:
        return dict(incoming)
    narrowed = {}
    for key, cur_val in current.items():
        if key not in incoming:
            # a key dropped from the incoming ceiling stays constrained
            narrowed[key] = cur_val
            continue
        inc_val = incoming[key]
        if isinstance(cur_val, list) and isinstance(inc_val, list):
            narrowed[key] = [x for x in cur_val if x in inc_val]
        else:
            narrowed[key] = inc_val if inc_val == cur_val else _INCOMPATIBLE
    # keys only present in the incoming ceiling further constrain
    for key, inc_val in incoming.items():
        if key not in narrowed:
            narrowed[key] = inc_val
    return narrowed


_INCOMPATIBLE = object()
