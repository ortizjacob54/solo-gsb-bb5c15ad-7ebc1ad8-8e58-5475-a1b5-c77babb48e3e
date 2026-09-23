"""请求 / 响应模型与输入校验。"""

from __future__ import annotations

from typing import List, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_INTERSECTIONS = 8
MAX_WINDOW_SECONDS = 3600  # 发车范围不超过一小时


class GreenInterval(BaseModel):
    """周期内的绿灯半开区间 [start, end)；start > end 表示跨周期零点。"""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(..., allow_inf_nan=False, description="绿灯起点（秒，周期内本地时刻，含端点）")
    end: float = Field(..., allow_inf_nan=False, description="绿灯终点（秒，周期内本地时刻，不含端点）")


class Intersection(BaseModel):
    """单个路口的信号与行驶时间参数。"""

    model_config = ConfigDict(extra="forbid")

    cycle: float = Field(..., ge=1.0, allow_inf_nan=False, description="信号周期（秒），>= 1")
    offset: float = Field(0.0, allow_inf_nan=False, description="相位偏移（秒），可为任意实数，默认 0")
    green: GreenInterval = Field(..., description="周期内绿灯半开区间，可跨周期零点")
    travel_time: float = Field(..., ge=0.0, allow_inf_nan=False, description="起点到该路口的固定行驶时间（秒），>= 0")

    @model_validator(mode="after")
    def _check_green(self) -> "Intersection":
        gs, ge, c = self.green.start, self.green.end, self.cycle
        if not 0.0 <= gs < c:
            raise ValueError(f"green.start 须满足 0 <= start < cycle（收到 start={gs}, cycle={c}）")
        if not 0.0 < ge <= c:
            raise ValueError(f"green.end 须满足 0 < end <= cycle（收到 end={ge}, cycle={c}）")
        if gs == ge:
            raise ValueError("green.start 与 green.end 不能相等（绿灯区间为空）")
        return self


class DepartureWindow(BaseModel):
    """整数秒半开发车范围 [start, end)，长度不超过一小时。"""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(..., ge=0, description="发车范围起点（整数秒，含端点）")
    end: int = Field(..., description="发车范围终点（整数秒，不含端点）")

    @model_validator(mode="after")
    def _check_range(self) -> "DepartureWindow":
        if self.end <= self.start:
            raise ValueError("departure_window.end 必须大于 start（半开区间）")
        if self.end - self.start > MAX_WINDOW_SECONDS:
            raise ValueError(f"发车范围长度不能超过 {MAX_WINDOW_SECONDS} 秒（一小时）")
        return self


class GreenWaveRequest(BaseModel):
    """发车窗口求解请求。"""

    model_config = ConfigDict(extra="forbid")

    departure_window: DepartureWindow
    intersections: List[Intersection] = Field(
        ..., min_length=1, max_length=MAX_INTERSECTIONS, description="路口列表，1~8 个"
    )


class Window(BaseModel):
    """一个极大半开发车区间 [start, end)（秒）。"""

    start: Union[int, float]
    end: Union[int, float]


class GreenWaveResponse(BaseModel):
    """全部极大半开发车区间，按起点升序；无解时 windows 为空数组。"""

    windows: List[Window]
    count: int
