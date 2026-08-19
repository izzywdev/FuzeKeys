"""Route-shape regression tests for the Google integration router.

Every one of these encodes a bug that shipped:

* `/signup/manual` was declared AFTER `/signup/{identity_id}`. Starlette matches
  in declaration order and the parameterised route also matches "manual", so it
  bound identity_id="manual" and failed int validation with a 422 —
  `manual_signup` was unreachable, and no test noticed because none called it.
* The frontend called `/accounts?identity_id=`, `/signup/identity` and
  `/test/identity/{id}`; the routes are `/accounts/{identity_id}`,
  `/signup/{identity_id}` and `/test/identity-conversion/{identity_id}`.

These assert the shapes the client depends on, so a rename on either side fails
here rather than in production.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from app.routers.auth import get_current_user

client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)


@pytest.fixture
def authed():
    """These routes are auth-gated, so without an override every assertion below
    would pass on a 403 and prove nothing about routing."""
    user = User(
        id=1,
        username="testuser",
        email="testuser@example.com",
        hashed_password="not-a-real-hash",
        master_key_hash="not-a-real-master-key-hash",
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


def _declared_paths() -> list[str]:
    return [getattr(r, "path", "") for r in app.routes]


class TestRouteDeclarationOrder:
    def test_signup_manual_is_declared_before_the_parameterised_signup(self):
        paths = _declared_paths()
        manual = paths.index("/api/google/signup/manual")
        param = paths.index("/api/google/signup/{identity_id}")
        assert manual < param, (
            "/signup/manual must be declared before /signup/{identity_id}: "
            "Starlette matches in order, and the parameterised route also matches "
            "'manual', making manual_signup unreachable"
        )

    def test_signup_manual_is_actually_reachable(self, authed):
        """The behavioural half — ordering is the cause, this is the symptom."""
        response = client.post("/api/google/signup/manual", json={})
        # 422 for a missing `signup_data` body is fine and expected; a 422 naming
        # `identity_id` means the parameterised route captured it again.
        detail = response.json().get("detail")
        captured_by_param_route = isinstance(detail, list) and any(
            "identity_id" in (item.get("loc") or []) for item in detail
        )
        assert (
            not captured_by_param_route
        ), f"/signup/manual was captured by /signup/{{identity_id}}: {detail}"


class TestRouteShapesTheClientDependsOn:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/google/accounts/{identity_id}",
            "/api/google/signup/{identity_id}",
            "/api/google/signup/manual",
            "/api/google/test/identity-conversion/{identity_id}",
            "/api/google/config/default",
        ],
    )
    def test_route_exists(self, path):
        assert path in _declared_paths(), f"{path} is gone — the frontend calls it"

    @pytest.mark.parametrize(
        "gone",
        [
            "/api/google/signup/identity",
            "/api/google/test/identity/{identity_id}",
        ],
    )
    def test_paths_the_frontend_used_to_guess_do_not_exist(self, gone):
        """Guards the other direction: if someone ever adds these as real routes,
        the client fix in this change becomes wrong and should be revisited."""
        assert gone not in _declared_paths()

    def test_accounts_takes_the_identity_in_the_path_not_the_query(self, authed):
        """The original bug: ?identity_id= matched no route at all."""
        assert client.get("/api/google/accounts?identity_id=1").status_code == 404
        assert client.get("/api/google/accounts/1").status_code != 404
