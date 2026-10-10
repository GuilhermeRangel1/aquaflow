from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_owner_can_query_ml_inferences_for_property(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, _, token = api_client
    response = await client.get(
        f"/api/v1/properties/{property_id}/ml-inferences",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"items": [], "limit": 50}


@pytest.mark.asyncio
async def test_ml_inferences_require_property_ownership(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, _, token = api_client
    headers = {"Authorization": f"Bearer {token}"}

    unauthorized = await client.get(f"/api/v1/properties/{property_id}/ml-inferences")
    forbidden = await client.get(
        f"/api/v1/properties/{uuid4()}/ml-inferences", headers=headers
    )

    assert unauthorized.status_code == 401
    assert forbidden.status_code == 404
