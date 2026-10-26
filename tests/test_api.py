import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from app import app  # noqa: E402


@pytest.fixture()
def client():
    return app.test_client()


def test_health(client):
    body = client.get("/health").get_json()
    assert body["status"] == "ok"
    assert body["last_history_date"] == "2019-05-31"


def test_stores(client):
    assert len(client.get("/stores").get_json()) == 365


def test_predict_single_and_batch(client):
    one = client.post("/predict", json={"store_id": 1, "date": "2019-06-03", "discount": "Yes"}).get_json()
    assert one["count"] == 1 and one["predictions"][0]["predicted_sales"] > 0

    rows = [{"store_id": 1, "date": f"2019-06-{d:02d}", "holiday": 0, "discount": d % 2} for d in range(1, 11)]
    batch = client.post("/predict", json=rows).get_json()
    assert batch["count"] == 10


def test_discount_raises_forecast(client):
    base = {"store_id": 42, "date": "2019-06-10", "holiday": 0}
    no = client.post("/predict", json={**base, "discount": 0}).get_json()["predictions"][0]["predicted_sales"]
    yes = client.post("/predict", json={**base, "discount": 1}).get_json()["predictions"][0]["predicted_sales"]
    assert yes > no


def test_far_horizon_uses_recursion(client):
    out = client.post("/predict", json={"store_id": 7, "date": "2019-10-15"}).get_json()
    assert out["predictions"][0]["predicted_sales"] > 0


@pytest.mark.parametrize("payload", [
    {"store_id": 999, "date": "2019-06-01"},
    {"store_id": 1, "date": "2019-05-01"},
    {"store_id": 1},
    {"store_id": 1, "date": "2019-06-01", "discount": "maybe"},
])
def test_bad_requests(client, payload):
    resp = client.post("/predict", json=payload)
    assert resp.status_code == 400 and "error" in resp.get_json()
