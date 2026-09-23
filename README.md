# 干线绿波发车窗口 API

基于 Python + FastAPI 的干线绿波（Green Wave）发车窗口计算服务。

给定干线上 **最多 8 个路口** 的信号周期、相位偏移、周期内绿灯半开区间，以及从起点到各路口的固定行驶时间，在 **不超过一小时的整数秒半开发车范围** 内，计算「抵达每个路口均遇绿灯」的 **全部极大半开发车区间**，按区间起点升序返回。

- 绿灯区间支持 **跨周期零点**（如 `[50, 10)` 表示每周期的 50~60 秒与 0~10 秒为绿灯）。
- 求解采用 **周期边界展开 + 半开区间求交** 的区间代数方法，**不逐秒试探**。
- 非法输入（周期、相位、绿灯端点、行驶时间、发车范围）返回 `422`；约束不可满足时返回空数组。

## 快速开始（一条命令）

需要 Docker 与 Docker Compose。在本目录执行：

```bash
docker compose up --build
```

启动后：

| 项目 | 地址 |
| --- | --- |
| API 地址 | `http://localhost:8000` |
| 计算接口 | `POST http://localhost:8000/api/v1/green-wave/departure-windows` |
| 交互式文档（Swagger UI） | `http://localhost:8000/docs` |
| 健康检查 | `GET http://localhost:8000/health` |

### 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8000` | 宿主机映射端口，如 `PORT=9000 docker compose up --build` 后访问 `http://localhost:9000` |

容器内服务固定监听 `8000`（Compose 将 `${PORT}` 映射到容器 `8000`）；如直接 `docker run`，可用 `-e PORT=<端口>` 改变容器内监听端口并自行映射。

## API 说明

### `POST /api/v1/green-wave/departure-windows`

#### 请求体

```json
{
  "departure_window": { "start": 0, "end": 130 },
  "intersections": [
    { "cycle": 60, "offset": 0, "green": { "start": 10, "end": 40 }, "travel_time": 15 },
    { "cycle": 60, "offset": 5, "green": { "start": 55, "end": 25 }, "travel_time": 75 }
  ]
}
```

| 字段 | 类型 | 约束 | 含义 |
| --- | --- | --- | --- |
| `departure_window.start` | int | `>= 0` | 发车范围起点（整数秒，**含**） |
| `departure_window.end` | int | `> start`，且 `end - start <= 3600` | 发车范围终点（整数秒，**不含**） |
| `intersections` | array | 1 ~ 8 个元素 | 路口列表 |
| `intersections[].cycle` | number | `>= 1` | 信号周期（秒） |
| `intersections[].offset` | number | 任意实数，缺省 `0` | 相位偏移（秒） |
| `intersections[].green.start` | number | `0 <= start < cycle` | 周期内绿灯起点（秒，**含**） |
| `intersections[].green.end` | number | `0 < end <= cycle`，且 `!= green.start` | 周期内绿灯终点（秒，**不含**） |
| `intersections[].travel_time` | number | `>= 0` | 起点到该路口的固定行驶时间（秒） |

**模型约定**

- 时刻 `tau` 时路口的本地相位为 `(tau - offset) mod cycle`。
- 发车时刻为 `T` 的车辆于 `T + travel_time` 到达路口，到达时本地相位须落在绿灯半开区间内。
- `green.start > green.end` 表示绿灯跨周期零点，即 `[start, cycle) ∪ [0, end)`。

#### 成功响应 `200`

返回全部极大半开发车区间 `[start, end)`，按起点升序；`count` 为区间个数。无解时 `windows` 为空数组。

```bash
curl -s -X POST http://localhost:8000/api/v1/green-wave/departure-windows \
  -H 'Content-Type: application/json' \
  -d '{
    "departure_window": {"start": 0, "end": 130},
    "intersections": [
      {"cycle": 60, "offset": 0, "green": {"start": 10, "end": 40}, "travel_time": 15},
      {"cycle": 60, "offset": 5, "green": {"start": 55, "end": 25}, "travel_time": 75}
    ]
  }'
```

```json
{
  "windows": [
    { "start": 0,   "end": 15  },
    { "start": 55,  "end": 75  },
    { "start": 115, "end": 130 }
  ],
  "count": 3
}
```

#### 参数校验失败 `422`

以下情况返回 `422 Unprocessable Entity`（响应体含具体错误位置与原因）：

- 周期 `cycle <= 0`（或小于 1 秒）、非数值、NaN/Inf；
- 相位偏移 `offset` 非数值或 NaN/Inf；
- 绿灯端点越界（`start` 不在 `[0, cycle)`、`end` 不在 `(0, cycle]`）或 `start == end`（空绿灯区间）；
- 行驶时间 `travel_time < 0`；
- 发车范围非整数秒、`start >= end`、长度超过 3600 秒、`start < 0`；
- 路口数量不在 1 ~ 8 之间；
- 请求体含未定义的多余字段。

## 本地开发（不用 Docker）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # 含运行与测试依赖
uvicorn app.main:app --reload --port 8000
```

运行测试：

```bash
pytest tests/ -q
```

## 求解方法

对每个路口，将「到达遇绿灯」条件平移回发车时刻轴，得到一族周期为 `cycle` 的半开区间
`[offset - travel_time + g0 + k*cycle, offset - travel_time + g1 + k*cycle)`（`k` 为整数）；
跨零点的绿灯先拆成 `[start, cycle)` 与 `[0, end)` 两段再分别展开。将各族区间在发车窗口内
展开、裁剪后做有序半开区间求交，最后把首尾相接的结果合并为极大区间。全程为区间代数运算，
复杂度与「窗口内信号周期数」成正比，不逐秒试探。

## 项目结构

```
.
├── app/
│   ├── main.py      # FastAPI 应用与路由
│   ├── models.py    # 请求/响应模型与输入校验
│   └── solver.py    # 区间展开、求交、合并的核心求解逻辑
├── tests/           # pytest 单元测试与 API 集成测试
├── requirements.txt       # 运行依赖
├── requirements-dev.txt   # 开发/测试依赖
├── Dockerfile
├── docker-compose.yml
└── README.md
```
