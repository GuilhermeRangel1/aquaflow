import csv
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.export_training_data import export_reviewed
from tests.conftest import reading_payload


async def _readings(
    client: AsyncClient,
    property_id: UUID,
    device_key: str,
    token: str,
    *,
    count: int = 2,
) -> tuple[UUID, list[UUID]]:
    headers = {"Authorization": f"Bearer {token}"}
    devices = await client.get("/api/v1/devices", headers=headers)
    assert devices.status_code == 200
    device_id = UUID(devices.json()["items"][0]["id"])
    reading_ids: list[UUID] = []
    now = datetime.now(UTC)
    for index in range(count):
        accepted = await client.post(
            "/api/v1/ingestion/telemetry",
            headers={"X-Device-Key": device_key},
            json=reading_payload(
                f"label-test-{uuid4().hex}",
                (now - timedelta(minutes=count - index)).isoformat(),
                cumulative_volume_liters=100 + index,
                flow_rate_liters_minute=0.2 + index,
            ),
        )
        assert accepted.status_code == 202
        reading_ids.append(UUID(accepted.json()["reading_id"]))
    return device_id, reading_ids


@pytest.mark.asyncio
async def test_root_can_list_unlabeled_readings_and_record_an_audited_label(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    device_id, reading_ids = await _readings(client, property_id, device_key, token)
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/api/v1/properties/{property_id}/telemetry-labels"

    listed = await client.get(path, params={"device_id": str(device_id)}, headers=headers)
    assert listed.status_code == 200
    by_id = {item["reading"]["id"]: item for item in listed.json()["items"]}
    assert by_id[str(reading_ids[0])]["current_label"] is None

    created = await client.post(
        path,
        headers=headers,
        json={
            "device_id": str(device_id),
            "reading_ids": [str(reading_ids[0])],
            "label": "anomaly",
            "notes": "Fluxo contínuo confirmado em teste controlado.",
        },
    )
    assert created.status_code == 201
    annotation = created.json()["items"][0]
    assert annotation["reading_id"] == str(reading_ids[0])
    assert annotation["device_id"] == str(device_id)
    assert annotation["label"] == "anomaly"
    assert annotation["notes"] == "Fluxo contínuo confirmado em teste controlado."
    assert annotation["reviewed_by_id"]
    assert annotation["reviewed_at"].endswith("Z") or "+00:00" in annotation["reviewed_at"]

    listed_again = await client.get(path, params={"device_id": str(device_id)}, headers=headers)
    refreshed = {item["reading"]["id"]: item for item in listed_again.json()["items"]}
    assert refreshed[str(reading_ids[0])]["current_label"]["label"] == "anomaly"


@pytest.mark.asyncio
async def test_export_uses_latest_review_and_tracks_exclusions(
    api_client: tuple[AsyncClient, UUID, str, str], tmp_path: Path
) -> None:
    client, property_id, device_key, token = api_client
    device_id, reading_ids = await _readings(client, property_id, device_key, token, count=3)
    path = f"/api/v1/properties/{property_id}/telemetry-labels"
    for reading_id, label in zip(
        [reading_ids[0], reading_ids[1], reading_ids[1]],
        ["normal", "anomaly", "ignored"],
        strict=True,
    ):
        response = await client.post(
            path,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "device_id": str(device_id),
                "reading_ids": [str(reading_id)],
                "label": label,
                "notes": "Conferido em ensaio controlado.",
            },
        )
        assert response.status_code == 201

    output = tmp_path / "reviewed.csv"
    end = datetime.now(UTC)
    count = await export_reviewed(
        client._transport.app.state.session_factory,  # type: ignore[attr-defined]
        device_id,
        end - timedelta(hours=1),
        end,
        "simulated",
        output,
    )
    assert count == 1
    with output.open(encoding="utf-8", newline="") as source:
        (row,) = list(csv.DictReader(source))
    assert row["reading_id"] == str(reading_ids[0])
    assert row["anomaly_label"] == "0"
    assert row["review_id"]
    manifest = json.loads(output.with_suffix(".csv.json").read_text(encoding="utf-8"))
    assert manifest["excluded_by_review_status"] == {"ignored": 1, "unlabeled": 1}
    assert manifest["sha256"] == sha256(output.read_bytes()).hexdigest()


@pytest.mark.asyncio
async def test_label_revision_is_append_only_and_history_is_visible(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    device_id, reading_ids = await _readings(client, property_id, device_key, token, count=1)
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/api/v1/properties/{property_id}/telemetry-labels"
    payload = {
        "device_id": str(device_id),
        "reading_ids": [str(reading_ids[0])],
        "notes": "Revisão manual após teste controlado.",
    }

    first = await client.post(path, headers=headers, json={**payload, "label": "anomaly"})
    second = await client.post(path, headers=headers, json={**payload, "label": "normal"})
    assert first.status_code == 201
    assert second.status_code == 201

    current = await client.get(path, params={"device_id": str(device_id)}, headers=headers)
    current_item = next(
        item for item in current.json()["items"] if item["reading"]["id"] == str(reading_ids[0])
    )
    assert current_item["current_label"]["label"] == "normal"

    history = await client.get(f"{path}/{reading_ids[0]}/history", headers=headers)
    assert history.status_code == 200
    assert [item["label"] for item in history.json()["items"]] == ["normal", "anomaly"]


@pytest.mark.asyncio
async def test_non_root_cannot_list_or_record_telemetry_labels(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    device_id, reading_ids = await _readings(client, property_id, device_key, token, count=1)
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Conta comum",
            "email": f"viewer-{uuid4().hex}@example.net",
            "password": "test-password-with-12",
        },
    )
    assert registration.status_code == 201
    viewer_headers = {"Authorization": f"Bearer {registration.json()['tokens']['access_token']}"}
    path = f"/api/v1/properties/{property_id}/telemetry-labels"

    listed = await client.get(path, headers=viewer_headers)
    created = await client.post(
        path,
        headers=viewer_headers,
        json={
            "device_id": str(device_id),
            "reading_ids": [str(reading_ids[0])],
            "label": "normal",
            "notes": "Período sem evento controlado.",
        },
    )
    assert listed.status_code == 403
    assert listed.json()["code"] == "admin_required"
    assert created.status_code == 403
    assert created.json()["code"] == "admin_required"


@pytest.mark.asyncio
async def test_batch_label_is_atomic_and_requires_anomaly_evidence(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    device_id, reading_ids = await _readings(client, property_id, device_key, token, count=1)
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/api/v1/properties/{property_id}/telemetry-labels"

    missing_evidence = await client.post(
        path,
        headers=headers,
        json={
            "device_id": str(device_id),
            "reading_ids": [str(reading_ids[0])],
            "label": "anomaly",
        },
    )
    mixed_batch = await client.post(
        path,
        headers=headers,
        json={
            "device_id": str(device_id),
            "reading_ids": [str(reading_ids[0]), str(uuid4())],
            "label": "normal",
            "notes": "Revisão manual.",
        },
    )
    assert missing_evidence.status_code == 422
    assert mixed_batch.status_code == 404

    history = await client.get(f"{path}/{reading_ids[0]}/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["items"] == []


@pytest.mark.asyncio
async def test_review_list_supports_timezone_range_and_cursor(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    device_id, reading_ids = await _readings(client, property_id, device_key, token)
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/api/v1/properties/{property_id}/telemetry-labels"
    now = datetime.now(UTC)

    first_page = await client.get(
        path,
        params={"device_id": str(device_id), "limit": 1},
        headers=headers,
    )
    assert first_page.status_code == 200
    assert first_page.json()["has_more"] is True
    assert first_page.json()["cursor"]
    next_page = await client.get(
        path,
        params={"device_id": str(device_id), "limit": 1, "cursor": first_page.json()["cursor"]},
        headers=headers,
    )
    assert next_page.status_code == 200
    assert next_page.json()["has_more"] is False
    assert (
        first_page.json()["items"][0]["reading"]["id"]
        != next_page.json()["items"][0]["reading"]["id"]
    )

    in_range = await client.get(
        path,
        params={
            "device_id": str(device_id),
            "start": (now - timedelta(minutes=10)).isoformat(),
            "end": (now + timedelta(minutes=1)).isoformat(),
        },
        headers=headers,
    )
    no_timezone = await client.get(
        path,
        params={"device_id": str(device_id), "start": now.replace(tzinfo=None).isoformat()},
        headers=headers,
    )
    assert in_range.status_code == 200
    assert {item["reading"]["id"] for item in in_range.json()["items"]} == {
        str(reading_id) for reading_id in reading_ids
    }
    assert no_timezone.status_code == 422
    assert no_timezone.json()["code"] == "timezone_required"


@pytest.mark.asyncio
async def test_label_routes_require_authentication(
    empty_api_client: AsyncClient,
) -> None:
    listed = await empty_api_client.get(f"/api/v1/properties/{uuid4()}/telemetry-labels")
    created = await empty_api_client.post(
        f"/api/v1/properties/{uuid4()}/telemetry-labels",
        json={
            "device_id": str(uuid4()),
            "reading_ids": [str(uuid4())],
            "label": "normal",
            "notes": "Anotação de teste.",
        },
    )
    assert listed.status_code == 401
    assert created.status_code == 401
