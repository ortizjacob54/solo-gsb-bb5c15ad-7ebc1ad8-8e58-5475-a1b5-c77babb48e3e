"""API 集成测试。"""

import copy

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

URL = "/api/v1/green-wave/departure-windows"

VALID_BODY = {
    "departure_window": {"start": 0, "end": 1800},
    "intersections": [
        {"cycle": 60, "offset": 0, "green": {"start": 10, "end": 40}, "travel_time": 15},
        {"cycle": 60, "offset": 5, "green": {"start": 55, "end": 25}, "travel_time": 75},
    ],
}


def _body(**overrides):
    body = copy.deepcopy(VALID_BODY)
    body.update(overrides)
    return body


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_valid_request_sorted_maximal_windows():
    resp = client.post(URL, json=VALID_BODY)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == len(data["windows"])
    starts = [w["start"] for w in data["windows"]]
    assert starts == sorted(starts)
    for w in data["windows"]:
        assert 0 <= w["start"] < w["end"] <= 1800
    assert data["windows"], "该算例应有解"


def test_no_solution_returns_empty_array():
    body = _body(intersections=[
        {"cycle": 60, "offset": 0, "green": {"start": 0, "end": 20}, "travel_time": 0},
        {"cycle": 60, "offset": 0, "green": {"start": 30, "end": 50}, "travel_time": 0},
    ])
    resp = client.post(URL, json=body)
    assert resp.status_code == 200
    assert resp.json() == {"windows": [], "count": 0}


def test_wraparound_green_accepted():
    body = _body(intersections=[
        {"cycle": 60, "offset": 0, "green": {"start": 50, "end": 10}, "travel_time": 0},
    ])
    resp = client.post(URL, json=body)
    assert resp.status_code == 200
    windows = resp.json()["windows"]
    assert {"start": 0, "end": 10} in windows
    assert {"start": 50, "end": 70} in windows


@pytest.mark.parametrize("intersection", [
    {"cycle": 0, "green": {"start": 10, "end": 40}, "travel_time": 15},      # 周期为 0
    {"cycle": -60, "green": {"start": 10, "end": 40}, "travel_time": 15},    # 周期为负
    {"cycle": 60, "green": {"start": -1, "end": 40}, "travel_time": 15},     # 绿灯起点越界
    {"cycle": 60, "green": {"start": 10, "end": 61}, "travel_time": 15},     # 绿灯终点越界
    {"cycle": 60, "green": {"start": 60, "end": 40}, "travel_time": 15},     # 绿灯起点等于周期
    {"cycle": 60, "green": {"start": 30, "end": 30}, "travel_time": 15},     # 绿灯区间为空
    {"cycle": 60, "green": {"start": 10, "end": 40}, "travel_time": -5},     # 行驶时间为负
    {"cycle": 60, "green": {"start": 10, "end": 40}, "travel_time": 15, "offset": "abc"},  # 相位非数值
])
def test_invalid_intersection_rejected(intersection):
    intersection.setdefault("offset", 0)
    resp = client.post(URL, json=_body(intersections=[intersection]))
    assert resp.status_code == 422


@pytest.mark.parametrize("window", [
    {"start": 10, "end": 10},        # 空区间
    {"start": 20, "end": 10},        # 终点早于起点
    {"start": 0, "end": 3601},       # 超过一小时
    {"start": -5, "end": 100},       # 起点为负
    {"start": 0, "end": 10.5},       # 非整数秒
])
def test_invalid_departure_window_rejected(window):
    resp = client.post(URL, json=_body(departure_window=window))
    assert resp.status_code == 422


def test_window_of_exactly_one_hour_accepted():
    resp = client.post(URL, json=_body(departure_window={"start": 0, "end": 3600}))
    assert resp.status_code == 200


def test_too_many_intersections_rejected():
    one = {"cycle": 60, "offset": 0, "green": {"start": 10, "end": 40}, "travel_time": 0}
    resp = client.post(URL, json=_body(intersections=[one] * 9))
    assert resp.status_code == 422


def test_eight_intersections_accepted():
    one = {"cycle": 60, "offset": 0, "green": {"start": 0, "end": 60}, "travel_time": 0}
    resp = client.post(URL, json=_body(intersections=[one] * 8))
    assert resp.status_code == 200
    assert resp.json()["windows"] == [{"start": 0, "end": 1800}]


def test_empty_intersections_rejected():
    resp = client.post(URL, json=_body(intersections=[]))
    assert resp.status_code == 422


def test_offset_defaults_to_zero():
    body = _body(intersections=[
        {"cycle": 60, "green": {"start": 0, "end": 30}, "travel_time": 0},
    ])
    resp = client.post(URL, json=body)
    assert resp.status_code == 200
    assert resp.json()["windows"][0] == {"start": 0, "end": 30}
