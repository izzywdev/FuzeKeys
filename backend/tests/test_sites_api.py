"""
Tests for the Sites API (`/api/v1/sites`).

The previous suite targeted `app.routers.sites` and patched
`app.routers.sites.get_db` -- a name that module does not define. It could
never have passed: `app/main.py` does not mount that router at all ("Temporarily
use mock sites router"), it defines and mounts an inline `sites_router` backed by
an in-process MOCK_SITES list. The file was quarantined behind a module-level
skip.

Rather than keep testing a module nothing serves, this suite tests the router
that IS mounted, so `/api/v1/sites` -- which the frontend calls -- has real
coverage today. Mounting the database-backed CRUD router in
`app/routers/sites.py` is a separate product decision; when it lands, the
request/response assertions here are the contract it has to keep, and only the
fixture data changes.
"""

import pytest
from httpx import AsyncClient

BASE = "/api/v1/sites"

# Names present in the mounted router's fixture data. Asserted as a subset
# wherever possible so adding a site does not break the suite.
KNOWN_SITE_NAMES = {"google", "github", "aws", "openai", "linkedin"}


class TestListSites:
    @pytest.mark.asyncio
    async def test_list_sites(self, client: AsyncClient):
        response = await client.get(f"{BASE}/")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert data, "the sites listing should not be empty"
        assert KNOWN_SITE_NAMES <= {site["name"] for site in data}

    @pytest.mark.asyncio
    async def test_site_response_shape(self, client: AsyncClient):
        """Fields the frontend renders must all be present on every row."""
        response = await client.get(f"{BASE}/")
        assert response.status_code == 200

        required = {
            "id",
            "name",
            "display_name",
            "url",
            "category",
            "signup_difficulty",
            "signin_difficulty",
            "apikey_difficulty",
            "overall_difficulty",
            "signup_status",
            "signin_status",
            "apikey_status",
            "implementation_progress",
            "priority",
            "anti_bot_techniques",
            "has_captcha",
        }
        for site in response.json():
            assert required <= set(site), f"missing keys on {site.get('name')}"

    @pytest.mark.asyncio
    async def test_pagination_skip_and_limit(self, client: AsyncClient):
        full = (await client.get(f"{BASE}/")).json()
        assert len(full) >= 3

        page = await client.get(f"{BASE}/?skip=0&limit=2")
        assert page.status_code == 200
        assert len(page.json()) == 2

        second = await client.get(f"{BASE}/?skip=2&limit=2")
        assert second.status_code == 200
        assert second.json() == full[2:4]

    @pytest.mark.asyncio
    async def test_pagination_does_not_overlap(self, client: AsyncClient):
        """Consecutive pages must not repeat a row -- the classic off-by-one."""
        first = (await client.get(f"{BASE}/?skip=0&limit=2")).json()
        second = (await client.get(f"{BASE}/?skip=2&limit=2")).json()

        first_ids = {site["id"] for site in first}
        second_ids = {site["id"] for site in second}
        assert first_ids.isdisjoint(second_ids)

    @pytest.mark.asyncio
    async def test_skip_beyond_end_returns_empty(self, client: AsyncClient):
        response = await client.get(f"{BASE}/?skip=10000&limit=10")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_negative_skip_is_rejected(self, client: AsyncClient):
        """skip is `ge=0`, so a negative offset is a 422, not a silent clamp."""
        response = await client.get(f"{BASE}/?skip=-1")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_zero_limit_is_rejected(self, client: AsyncClient):
        """limit is `ge=1`; a zero limit would otherwise return an empty page."""
        response = await client.get(f"{BASE}/?limit=0")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_limit_above_maximum_is_rejected(self, client: AsyncClient):
        """`le=1000` is the guard against an unbounded page."""
        response = await client.get(f"{BASE}/?limit=1001")
        assert response.status_code == 422


class TestFilterSites:
    @pytest.mark.asyncio
    async def test_filter_by_category(self, client: AsyncClient):
        response = await client.get(f"{BASE}/?category=developer-tools")
        assert response.status_code == 200

        data = response.json()
        assert data
        assert all(site["category"] == "developer-tools" for site in data)

    @pytest.mark.asyncio
    async def test_filter_by_unknown_category_is_empty(self, client: AsyncClient):
        response = await client.get(f"{BASE}/?category=no-such-category")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_filter_by_priority_min(self, client: AsyncClient):
        response = await client.get(f"{BASE}/?priority_min=90")
        assert response.status_code == 200

        data = response.json()
        assert data
        assert all(site["priority"] >= 90 for site in data)

    @pytest.mark.asyncio
    async def test_priority_min_out_of_range_is_rejected(self, client: AsyncClient):
        """priority_min is `ge=1, le=100`."""
        assert (await client.get(f"{BASE}/?priority_min=0")).status_code == 422
        assert (await client.get(f"{BASE}/?priority_min=101")).status_code == 422

    @pytest.mark.asyncio
    async def test_filter_by_difficulty_matches_any_axis(self, client: AsyncClient):
        """`difficulty` matches signup OR signin OR apikey, not just one."""
        response = await client.get(f"{BASE}/?difficulty=easy")
        assert response.status_code == 200

        data = response.json()
        assert data
        for site in data:
            assert "easy" in {
                site["signup_difficulty"],
                site["signin_difficulty"],
                site["apikey_difficulty"],
            }

    @pytest.mark.asyncio
    async def test_search_matches_name(self, client: AsyncClient):
        response = await client.get(f"{BASE}/?search=github")
        assert response.status_code == 200

        data = response.json()
        assert [site["name"] for site in data] == ["github"]

    @pytest.mark.asyncio
    async def test_search_is_case_insensitive(self, client: AsyncClient):
        lower = (await client.get(f"{BASE}/?search=github")).json()
        upper = (await client.get(f"{BASE}/?search=GITHUB")).json()
        assert lower == upper

    @pytest.mark.asyncio
    async def test_search_matches_description(self, client: AsyncClient):
        """Search covers name, display_name and description."""
        response = await client.get(f"{BASE}/?search=cloud")
        assert response.status_code == 200
        assert {site["name"] for site in response.json()}

    @pytest.mark.asyncio
    async def test_search_with_no_match_is_empty(self, client: AsyncClient):
        response = await client.get(f"{BASE}/?search=zzz-no-such-site-zzz")
        assert response.status_code == 200
        assert response.json() == []


class TestSortSites:
    @pytest.mark.asyncio
    async def test_default_sort_is_priority_descending(self, client: AsyncClient):
        response = await client.get(f"{BASE}/")
        assert response.status_code == 200

        priorities = [site["priority"] for site in response.json()]
        assert priorities == sorted(priorities, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_name_ascending(self, client: AsyncClient):
        response = await client.get(f"{BASE}/?sort_by=name&sort_order=asc")
        assert response.status_code == 200

        names = [site["name"] for site in response.json()]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_sort_by_priority_ascending(self, client: AsyncClient):
        response = await client.get(f"{BASE}/?sort_by=priority&sort_order=asc")
        assert response.status_code == 200

        priorities = [site["priority"] for site in response.json()]
        assert priorities == sorted(priorities)

    @pytest.mark.asyncio
    async def test_unknown_sort_field_is_rejected(self, client: AsyncClient):
        """sort_by is pattern-constrained, so an arbitrary column is a 422."""
        response = await client.get(f"{BASE}/?sort_by=notacolumn")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_sort_order_is_rejected(self, client: AsyncClient):
        response = await client.get(f"{BASE}/?sort_order=sideways")
        assert response.status_code == 422


class TestGetSite:
    @pytest.mark.asyncio
    async def test_get_site_by_id(self, client: AsyncClient):
        listed = (await client.get(f"{BASE}/")).json()
        expected = listed[0]

        response = await client.get(f"{BASE}/{expected['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == expected["id"]
        assert response.json()["name"] == expected["name"]

    @pytest.mark.asyncio
    async def test_get_unknown_site_is_404(self, client: AsyncClient):
        response = await client.get(f"{BASE}/999999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Site not found"

    @pytest.mark.asyncio
    async def test_non_integer_site_id_is_422(self, client: AsyncClient):
        """`/{site_id}` is typed `int`, so a slug is a validation error.

        This also pins the route ORDER: `/categories` and `/stats/overview` are
        declared before `/{site_id}`, so they resolve as literals. If someone
        moves the parameterised route above them, those two would be captured
        here and start returning 422 instead of their payloads -- which is what
        the next two tests catch.
        """
        response = await client.get(f"{BASE}/not-an-id")
        assert response.status_code == 422


class TestSitesMetadata:
    @pytest.mark.asyncio
    async def test_categories(self, client: AsyncClient):
        response = await client.get(f"{BASE}/categories")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert data
        for category in data:
            assert set(category) == {"name", "count"}
            assert isinstance(category["count"], int)

    @pytest.mark.asyncio
    async def test_stats_overview(self, client: AsyncClient):
        response = await client.get(f"{BASE}/stats/overview")
        assert response.status_code == 200

        data = response.json()
        assert {"total_sites", "categories", "implementation_progress"} <= set(data)
        assert isinstance(data["total_sites"], int)
        assert isinstance(data["categories"], list)


class TestSitesRouting:
    @pytest.mark.asyncio
    async def test_unversioned_path_is_not_served(self, client: AsyncClient):
        """`/api/sites` must not exist -- the mount is versioned."""
        response = await client.get("/api/sites")
        assert response.status_code == 404
