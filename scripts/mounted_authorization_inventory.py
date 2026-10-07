"""Inventory the actual FastAPI mounts, including hidden HTTP and WebSocket routes.

This is a reviewed release inventory, not a replacement for authorization gates.
Unknown endpoints remain explicit design gaps; inspecting a guard is not a live
permission proof. Importing the app does not run startup hooks or create grants.
"""

import argparse
import ast
import inspect
import json
from collections import Counter
from pathlib import Path


def walk_routes(routes, prefix=""):
    for route in routes:
        # FastAPI 0.135 lazily includes routers. Older versions flatten them.
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from walk_routes(
                original.routes, prefix + route.include_context.prefix
            )
        elif getattr(route, "endpoint", None) is not None:
            yield prefix + route.path, route


def guard_helpers(endpoint):
    module = inspect.getmodule(endpoint)
    if not module or not getattr(module, "__file__", None):
        return []
    source = Path(module.__file__).read_text()
    nodes = {
        node.name: node
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    seen, guards = set(), set()

    def visit(name):
        if name in seen or name not in nodes:
            return
        seen.add(name)
        for call in ast.walk(nodes[name]):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                continue
            callee = call.func.id
            if callee in {
                "require_owner_permission",
                "require_delegated_owner_permission",
                "require_connector_permission",
            }:
                guards.add(callee)
            visit(callee)

    visit(endpoint.__name__)
    return sorted(guards)


def dependency_names(route):
    names = set()

    def visit(dependant):
        call = getattr(dependant, "call", None)
        if callable(call):
            names.add(
                call.__module__ + "." + getattr(call, "__name__", type(call).__name__)
            )
        for child in getattr(dependant, "dependencies", []):
            visit(child)

    for child in getattr(getattr(route, "dependant", None), "dependencies", []):
        visit(child)
    return sorted(names)


def assess(module, endpoint, method, helpers):
    if module == "app.routers.connectors":
        return (
            "instance_enforced_with_staged_registration",
            "Trusted delegation, tenant-scoped SQL/vault custody and exact Connector decisions; first PUT stages only non-secret owner intent (202). Live policy/grants remain required.",
        )
    if helpers:
        if (module, endpoint) in {
            ("app.routers.accounts", "create_account"),
            ("app.routers.google_integration", "signup_with_identity"),
        }:
            return (
                "parent_instance_enforced_child_lifecycle_gap",
                "Owned Identity:use is required before automation or writes; new Account grant creation/reconciliation is still unfinished.",
            )
        if (module, endpoint) == ("app.routers.chat", "chat_message"):
            return (
                "signup_branch_enforced_general_ai_gap",
                "Signup branch requires SQL-owned Identity:use; general AI chat/cost controls have no platform resource contract.",
            )
        return (
            "instance_enforced",
            "SQL ownership and immutable verified mapping plus exact instance allow precede response, decryption or mutation. Live mappings/grants remain required.",
        )
    if module == "app.routers.auth" and endpoint in {"register", "login"}:
        return (
            "enrollment_proof_boundary",
            "Pre-session registration/login cannot require an existing user instance grant. Password/master-key proof stays required; this inventory does not certify enrollment rate limits or deployment controls.",
        )
    if module == "app.routers.platform_identity":
        return (
            "dual_session_proof_boundary",
            "Local session plus trusted Security active tenant-membership proof creates an immutable mapping; no grants are created.",
        )
    if module == "app.routers.sms" and endpoint in {
        "receive_otp",
        "get_otp_requests",
        "sms_interceptor_websocket",
    }:
        return (
            "device_proof_platform_migration_gap",
            "Active device proof uses a durable SHA-256 key digest and callbacks require a creator-owned durable assignment; verified tenant mapping and platform instance policy remain.",
        )
    if module == "app.routers.infrastructure" and endpoint in {
        "complete_sms_verification",
        "mobile_commands_websocket",
    }:
        return (
            "device_proof_platform_migration_gap",
            "Durable active-device proof precedes socket acceptance or callback mutation, and callbacks require prior assignment; verified tenant mapping and platform instance policy remain.",
        )
    if module == "app.routers.sms" and endpoint == "register_device":
        return (
            "enrollment_token_platform_mapping_gap",
            "A strong out-of-band enrollment token gates atomic durable digest issuance/rotation. Device attestation, verified tenant ownership and platform grants remain.",
        )
    if module == "app.routers.sms" and endpoint == "assign_otp_request":
        return (
            "durable_local_owner_platform_mapping_gap",
            "The authenticated local creator may bind its durable request to one active durable device. Immutable platform subject/tenant mapping and an exact Security instance decision remain.",
        )
    if module == "app.routers.sms" and endpoint in {
        "request_otp",
        "get_request_status",
        "get_devices",
    }:
        return (
            "durable_local_owner_platform_mapping_gap",
            "Durable SQL creator/device scoping is enforced locally. Immutable platform subject/tenant mapping and exact instance policy remain.",
        )
    if module == "app.routers.sms" and endpoint == "health_check":
        return (
            "public_health",
            "Health returns only coarse connection/request counts; no device id, OTP or owner resource is projected.",
        )
    if module == "app.routers.credentials" and endpoint == "validate_credentials":
        return (
            "verified_delegated_input_validation",
            "Verified workload/delegation tokens, audience, actor binding and credential-write scope precede in-memory format validation; no stored resource is read or changed.",
        )
    if module == "app.routers.credentials" and endpoint == "health_check":
        return (
            "public_health",
            "Health response exposes no credential values or persisted owner resource.",
        )
    if module == "app.routers.broker" and endpoint == "revoke":
        return (
            "verified_workload_sql_owner_tenant_policy_gap",
            "SDK-verified fuze-workload token for service:fuzekeys plus exact SQL grantor principal permits revocation; caller-asserted gateway headers are ignored. Stored grants still lack verified tenant/platform instance policy mapping.",
        )
    if module == "app.routers.broker":
        return (
            "broker_platform_mapping_gap",
            "Existing broker service-key/macaroon proof and caveats remain; this is not proof of platform resource-instance policy migration.",
        )
    if module == "app.main" and endpoint == "demo_chat":
        return (
            "public_static_demo",
            "Returns canned in-source strings; no provider request, database mutation or secret is performed.",
        )
    if module == "fastapi.applications":
        return (
            "public_framework_documentation",
            "Framework schema/UI endpoint. Credential/session-bound routes stay excluded from generated schema.",
        )
    if module == "app.main" and method == "GET":
        return (
            "public_health_or_static_catalog",
            "Health/info or in-source demo/site catalog; real routers/sites.py mutation endpoints are not mounted.",
        )
    if module == "app.routers.site_integrations" and endpoint in {
        "list_available_sites",
        "get_site_capabilities_endpoint",
        "integration_health_check",
    }:
        return (
            "public_catalog_or_health",
            "Provider integration discovery/health; no persisted owned resource is read or changed.",
        )
    if module == "app.routers.auth" and endpoint == "get_current_user_info":
        return (
            "local_session_profile",
            "Reads the authenticated local session's own User profile; platform session federation remains separate.",
        )
    return (
        "platform_policy_design_gap",
        "Existing authentication/proof dependencies are inventoried below. No reviewed complete resource/tenant/instance permission contract is implemented for this mounted endpoint.",
    )


def build_inventory(app):
    entries = []
    for path, route in walk_routes(app.routes):
        endpoint = route.endpoint
        module = endpoint.__module__
        helpers = guard_helpers(endpoint) if module.startswith("app.") else []
        methods = sorted(getattr(route, "methods", None) or ["WEBSOCKET"])
        for method in methods:
            assessment, reason = assess(module, endpoint.__name__, method, helpers)
            entries.append(
                {
                    "method": method,
                    "path": path,
                    "endpoint": module + "." + endpoint.__name__,
                    "include_in_schema": getattr(route, "include_in_schema", False),
                    "dependencies": dependency_names(route),
                    "guard_helpers": helpers,
                    "assessment": assessment,
                    "reason": reason,
                }
            )
    return {
        "source": "actual app.main FastAPI mounts; startup/deployment not executed",
        "production_verified": False,
        "route_method_count": len(entries),
        "mutating_http_count": sum(
            e["method"] in {"POST", "PUT", "PATCH", "DELETE"} for e in entries
        ),
        "assessment_counts": dict(
            sorted(Counter(e["assessment"] for e in entries).items())
        ),
        "not_mounted": [
            "app.routers.background",
            "app.routers.sites (real database CRUD/import; app.main mounts its static sites_router instead)",
        ],
        "routes": entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    from app.main import app

    Path(args.output).write_text(json.dumps(build_inventory(app), indent=2) + "\n")


if __name__ == "__main__":
    main()
