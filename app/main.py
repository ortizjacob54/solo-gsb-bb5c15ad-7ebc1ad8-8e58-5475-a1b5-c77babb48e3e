"""FastAPI 应用入口。"""

from __future__ import annotations

from typing import Union

from fastapi import FastAPI

from .models import GreenWaveRequest, GreenWaveResponse, Window
from .solver import IntersectionSpec, compute_departure_windows

app = FastAPI(
    title="干线绿波发车窗口 API",
    description=(
        "给定干线上最多 8 个路口的信号周期、相位偏移、周期内绿灯半开区间及固定行驶时间，"
        "在不超过一小时的整数秒半开发车范围内，求抵达每个路口均遇绿灯的全部极大半开发车区间。"
    ),
    version="1.0.0",
)


def _as_number(x: float) -> Union[int, float]:
    """整数值以 int 输出，非整数保留 float。"""
    return int(x) if float(x).is_integer() else x


@app.get("/health", tags=["meta"], summary="健康检查")
def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/api/v1/green-wave/departure-windows",
    response_model=GreenWaveResponse,
    tags=["green-wave"],
    summary="计算干线绿波的极大半开发车区间",
)
def departure_windows(request: GreenWaveRequest) -> GreenWaveResponse:
    specs = [
        IntersectionSpec(
            cycle=item.cycle,
            offset=item.offset,
            green_start=item.green.start,
            green_end=item.green.end,
            travel_time=item.travel_time,
        )
        for item in request.intersections
    ]
    raw = compute_departure_windows(
        specs,
        float(request.departure_window.start),
        float(request.departure_window.end),
    )
    windows = [Window(start=_as_number(s), end=_as_number(e)) for s, e in raw]
    return GreenWaveResponse(windows=windows, count=len(windows))
