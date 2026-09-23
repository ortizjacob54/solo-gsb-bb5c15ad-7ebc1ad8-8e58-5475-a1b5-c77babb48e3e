"""干线绿波发车窗口的核心求解逻辑。

模型约定
--------
- 时间轴为绝对秒数，发车时刻记为 T。
- 路口 i 的信号本地相位（时刻 tau 时）定义为: phase_i(tau) = (tau - offset_i) mod cycle_i。
- 绿灯为周期内的半开区间 [green_start, green_end)；当 green_start > green_end 时
  表示绿灯跨周期零点，即 [green_start, cycle) ∪ [0, green_end)。
- 车辆 T 时刻发车，到达路口 i 的时刻为 T + travel_time_i，要求到达时相位落在绿灯内。

求解方法
--------
对每个路口，把“到达遇绿灯”的条件平移回发车时刻轴，得到一族周期为 cycle 的
半开区间 [offset - travel + g0 + k*cycle, offset - travel + g1 + k*cycle)（k 为整数）。
将每族区间在发车窗口内展开（跨周期零点时展开为两段），再对各族做有序半开区间求交，
最后把首尾相接的结果合并为极大区间。全程为区间代数运算，不逐秒试探。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

# 半开区间 [start, end)
Interval = Tuple[float, float]


@dataclass(frozen=True)
class IntersectionSpec:
    """单个路口的求解输入（数值已经过 API 层校验）。"""

    cycle: float        # 信号周期（秒），> 0
    offset: float       # 相位偏移（秒），任意实数
    green_start: float  # 周期内绿灯起点（秒，含）
    green_end: float    # 周期内绿灯终点（秒，不含）
    travel_time: float  # 起点到该路口的固定行驶时间（秒），>= 0


def _green_segments(green_start: float, green_end: float, cycle: float) -> List[Interval]:
    """把可能跨周期零点的绿灯区间拆成周期 [0, cycle) 内的普通半开段。"""
    if green_start < green_end:
        return [(green_start, green_end)]
    # green_start > green_end：跨零点，拆成两段
    return [(green_start, cycle), (0.0, green_end)]


def _intersection_windows(spec: IntersectionSpec, win_start: float, win_end: float) -> List[Interval]:
    """该路口“到达遇绿灯”对应的发车时刻区间（已裁剪到发车窗口内，升序、互不重叠）。"""
    # 发车时刻 T 满足: (T + travel - offset) mod cycle ∈ 绿灯区间
    # 即 T ∈ [offset - travel + g0 + k*cycle, offset - travel + g1 + k*cycle), k ∈ Z
    base = spec.offset - spec.travel_time
    cycle = spec.cycle
    windows: List[Interval] = []
    for seg_start, seg_end in _green_segments(spec.green_start, spec.green_end, cycle):
        a = base + seg_start
        b = base + seg_end
        # 只需展开与 [win_start, win_end) 有交集的周期；k 范围取宽一格，裁剪后过滤空区间
        k_lo = math.floor((win_start - b) / cycle) - 1
        k_hi = math.ceil((win_end - a) / cycle) + 1
        for k in range(k_lo, k_hi + 1):
            start = a + k * cycle
            end = b + k * cycle
            lo = max(start, win_start)
            hi = min(end, win_end)
            if lo < hi:
                windows.append((lo, hi))
    windows.sort()
    return windows


def _intersect(a_list: Sequence[Interval], b_list: Sequence[Interval]) -> List[Interval]:
    """两列升序、互不重叠的半开区间求交，结果仍升序、互不重叠。"""
    result: List[Interval] = []
    i = j = 0
    while i < len(a_list) and j < len(b_list):
        a_start, a_end = a_list[i]
        b_start, b_end = b_list[j]
        start = max(a_start, b_start)
        end = min(a_end, b_end)
        if start < end:
            result.append((start, end))
        if a_end < b_end:
            i += 1
        elif b_end < a_end:
            j += 1
        else:
            i += 1
            j += 1
    return result


def _merge_adjacent(intervals: Sequence[Interval]) -> List[Interval]:
    """把首尾相接（前一段终点 == 后一段起点）的半开区间合并为极大区间。"""
    merged: List[Interval] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            prev_start, prev_end = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def compute_departure_windows(
    intersections: Sequence[IntersectionSpec],
    win_start: float,
    win_end: float,
) -> List[Interval]:
    """返回发车窗口 [win_start, win_end) 内、抵达所有路口均遇绿灯的极大半开区间（按起点升序）。"""
    result: List[Interval] = [(win_start, win_end)]
    for spec in intersections:
        result = _intersect(result, _intersection_windows(spec, win_start, win_end))
        if not result:  # 提前退出：已无解
            break
    return _merge_adjacent(result)
