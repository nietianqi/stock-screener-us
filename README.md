# US Swing Scanner (Longbridge Edition)

基于 Longbridge OpenAPI 的美股中线候选池扫描器，按 `TrendMomentum + PriceVolumeHealth + Catalyst + MicroFlow + RiskControl` 输出候选池、因子拆解、触发标签和排除原因。

## 特性

- 认证方式使用 Longbridge OAuth 2.0
- 主数据源只依赖 Longbridge v1 可直接获取的数据
- 支持静态信息、实时行情、历史日线、逐笔、盘口、资金流、filings、news/topics、option chain
- 外部增强因子保留为空值，不会导致程序失败
- 输出 CSV、HTML，并缓存到 SQLite / Parquet

## 目录

```text
app/
  config.py
  data_sources/
  factors/
  pipelines/
  reports/
  scoring/
  storage/
  utils/
main.py
```

## 安装

```bash
pip install -r requirements.txt
```

## 配置

1. 复制 `.env.example` 为 `.env`
2. 填入 `LONGBRIDGE_CLIENT_ID`
3. 首次运行时根据控制台输出的 URL 完成授权

Longbridge SDK 会把 token 缓存到本地，后续运行可直接复用。

## 股票池

默认读取 `data/universe_sample.csv`，也可以用参数覆盖：

```bash
python main.py scan --symbols AAPL.US,MSFT.US,NVDA.US
python main.py scan --universe-file data/my_universe.csv
```

CSV 至少包含：

```csv
symbol,industry_etf_proxy
AAPL.US,XLK.US
MSFT.US,XLK.US
```

## 运行

```bash
python main.py scan --top-n 20
python main.py weekly --top-n 30
```

输出目录默认为 `outputs/<scan_date>/`：

- `candidates.csv`
- `failures.csv`
- `candidates.html`

## v1 因子

- `avg_daily_value_20d`
- `ma50` / `ma200`
- `momentum_12_1`
- `rs_vs_spy` / `rs_vs_qqq` / `rs_vs_sector`
- `breakout_20d` / `breakout_60d`
- `vol_ratio_5_20`
- `accumulation_score`
- `earnings_gap_score`
- `filings_event_score`
- `option_activity_score`
- `capital_flow_score`
- `depth_bias_score`
- `risk_score`
- `total_score`

## 注意

- symbol 必须使用 `ticker.region` 格式，例如 `AAPL.US`
- 批量 quote / static_info 单次请求限制按 500 只分批
- 历史 K 线使用 `history_candlesticks_by_offset`
- 可选增强字段如 analyst revisions / 13F / short interest / buyback execution 仅保留接口位，不在 v1 强制实现
