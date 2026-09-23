"""求解器单元测试：手工算例 + 随机采样交叉验证。"""

import random

from app.solver import IntersectionSpec, compute_departure_windows


def spec(cycle, offset, green_start, green_end, travel_time):
    return IntersectionSpec(
        cycle=cycle, offset=offset, green_start=green_start,
        green_end=green_end, travel_time=travel_time,
    )


def test_single_intersection_basic():
    # (T + 15) mod 60 ∈ [10, 40)  =>  T ∈ [-5+60k, 25+60k)
    s = spec(cycle=60, offset=0, green_start=10, green_end=40, travel_time=15)
    assert compute_departure_windows([s], 0, 120) == [(0, 25), (55, 85), (115, 120)]


def test_green_wraps_across_cycle_zero():
    # 绿灯 [50, 10) 跨零点 => 相位 ∈ [50,60) ∪ [0,10)
    s = spec(cycle=60, offset=0, green_start=50, green_end=10, travel_time=0)
    assert compute_departure_windows([s], 0, 130) == [(0, 10), (50, 70), (110, 130)]


def test_offset_shifts_windows():
    # 相位偏移 20：到达时刻 tau 的本地相位为 (tau - 20) mod 60
    s = spec(cycle=60, offset=20, green_start=10, green_end=40, travel_time=0)
    assert compute_departure_windows([s], 0, 120) == [(30, 60), (90, 120)]


def test_intersection_of_two_intersections():
    a = spec(cycle=60, offset=0, green_start=10, green_end=40, travel_time=15)
    b = spec(cycle=60, offset=0, green_start=20, green_end=50, travel_time=45)
    # a: T ∈ [-5+60k, 25+60k)；b: T ∈ [-25+60k, 5+60k)
    # 交: [-5, 5), [55, 65), [115, 125) ... 窗口 [0, 120) 内 => [0,5), [55,65), [115,120)
    assert compute_departure_windows([a, b], 0, 120) == [(0, 5), (55, 65), (115, 120)]


def test_no_solution_returns_empty():
    a = spec(cycle=60, offset=0, green_start=0, green_end=20, travel_time=0)
    b = spec(cycle=60, offset=0, green_start=30, green_end=50, travel_time=0)
    assert compute_departure_windows([a, b], 0, 3600) == []


def test_full_cycle_green_merges_to_single_interval():
    # 全周期绿灯 [0, 60)：相邻周期区间首尾相接，应合并为一个极大区间
    s = spec(cycle=60, offset=0, green_start=0, green_end=60, travel_time=0)
    assert compute_departure_windows([s], 0, 200) == [(0, 200)]


def test_window_clips_result():
    s = spec(cycle=60, offset=0, green_start=0, green_end=30, travel_time=0)
    assert compute_departure_windows([s], 10, 70) == [(10, 30), (60, 70)]


def test_fractional_parameters():
    s = spec(cycle=59.5, offset=0.5, green_start=5.5, green_end=30.25, travel_time=2.5)
    result = compute_departure_windows([s], 0, 120)
    # T ∈ [0.5 - 2.5 + 5.5 + 59.5k, 0.5 - 2.5 + 30.25 + 59.5k) = [3.5 + 59.5k, 28.25 + 59.5k)
    assert result == [(3.5, 28.25), (63.0, 87.75)]


def _green_at(s: IntersectionSpec, t: float) -> bool:
    phase = (t + s.travel_time - s.offset) % s.cycle
    if s.green_start < s.green_end:
        return s.green_start <= phase < s.green_end
    return phase >= s.green_start or phase < s.green_end


def test_randomized_cross_check_against_sampling():
    rng = random.Random(20260923)
    for _ in range(300):
        n = rng.randint(1, 5)
        specs = []
        for _ in range(n):
            cycle = rng.choice([40, 50, 60, 70, 80, 90, 120])
            offset = rng.randint(-30, 90)
            gs = rng.randint(0, cycle - 1)
            ge = rng.randint(1, cycle)
            while ge == gs:
                ge = rng.randint(1, cycle)
            travel = rng.randint(0, 300)
            specs.append(spec(cycle, offset, gs, ge, travel))
        win_start = rng.randint(0, 600)
        win_end = win_start + rng.randint(1, 3600)
        result = compute_departure_windows(specs, win_start, win_end)

        # 结果自身性质：升序、互不重叠、落在窗口内
        for (s0, e0), (s1, e1) in zip(result, result[1:]):
            assert s0 < e0 <= s1 < e1
            assert e0 < s1  # 极大性：相邻结果之间必须有间隙
        for s0, e0 in result:
            assert win_start <= s0 < e0 <= win_end

        # 随机采样点：在结果内 <=> 所有路口遇绿灯
        for _ in range(200):
            t = rng.uniform(win_start, win_end)
            inside = any(s0 <= t < e0 for s0, e0 in result)
            expect = all(_green_at(s, t) for s in specs)
            assert inside == expect, (t, result, specs)
