# 5min BTC Polymarket - 机构级量化交易系统

开源的Polymarket BTC 5分钟高频预测系统，具备完整的数学模型、风控系统和纸面交易功能。

Repository: https://github.com/Novals83/5min-btc-polymarket

## 📊 系统特性

- ✅ **多源数据聚合**: Binance L2订单簿 + Deribit期权IV + Hyperliquid备用
- ✅ **数学模型**: GBM胜率预测 + OBI订单簿分析 + ATR动态阈值 + EV期望值校验
- ✅ **风控系统**: 凯利公式仓位管理 + 熔断器（每日亏损/连续亏损/回撤控制）
- ✅ **执行策略**: 狙击模式（最后5秒高胜率入场）+ 延迟优化
- ✅ **纸面交易**: 真实数据 + 模拟交易 + 完整盈亏统计
- ✅ **监控告警**: Telegram通知 + CSV数据记录 + 回测引擎

## 📁 项目结构

```
5min-btc-polymarket/
├── config/
│   └── btc_5m_profiles.yaml          # 策略配置（conservative/aggressive）
├── src/
│   ├── data_sources/                 # 数据源层
│   │   ├── aggregator.py             # 数据聚合器
│   │   ├── binance_ws.py             # 币安WebSocket（订单簿+主动买卖流）
│   │   ├── deribit_ws.py             # Deribit期权IV数据
│   │   ├── hyperliquid_ws.py         # Hyperliquid备用数据
│   │   ├── polymarket_api.py         # Polymarket公开API（无需密钥）
│   │   └── simulator.py              # 市场数据模拟器
│   ├── models/                       # 数学模型层
│   │   ├── gbm.py                    # 几何布朗运动（胜率预测）
│   │   ├── obi.py                    # 订单簿不平衡度
│   │   ├── atr.py                    # ATR动态波动率阈值
│   │   └── ev_calculator.py          # 期望值校验
│   ├── risk/                         # 风控层
│   │   ├── kelly_criterion.py        # 凯利公式仓位管理
│   │   └── circuit_breaker.py        # 熔断风控系统
│   ├── execution/                    # 执行层
│   │   ├── sniper.py                 # 狙击模式（最后5秒入场）
│   │   ├── latency_optimizer.py      # 延迟优化
│   │   └── paper_trading.py          # 纸面交易引擎
│   ├── monitoring/                   # 监控层
│   │   ├── dashboard.py              # 终端实时仪表盘（Rich）
│   │   ├── web_dashboard.py          # Web浏览器仪表盘
│   │   ├── notifier.py               # Telegram通知
│   │   └── data_logger.py            # CSV数据记录
│   ├── backtesting/                  # 回测层
│   │   └── engine.py                 # 回测引擎
│   └── core/
│       └── trade_runner.py           # 核心交易运行器
├── tests/                            # 测试
│   ├── test_gbm.py
│   ├── test_kelly.py
│   └── test_circuit_breaker.py
├── scripts/                          # 脚本
│   ├── deploy/vps_setup.sh           # VPS部署脚本
│   └── btc5m_ctl.sh                  # 控制脚本
├── requirements.txt                  # Python依赖
└── README.md                         # 本文档
```

## 🚀 快速开始

### 1. 安装

```bash
# 克隆项目
git clone https://github.com/Novals83/5min-btc-polymarket.git
cd 5min-btc-polymarket

# 创建conda环境
conda create -n btc5m python=3.10 -y
conda activate btc5m

# 安装依赖
pip install -r requirements.txt
```

### 2. 运行测试

```bash
# 运行单元测试（29个测试）
python -m pytest tests/ -v
```

### 3. 运行模式

系统支持 **6 种运行模式**，可通过命令行参数组合使用：

#### 📊 纸面交易模式（推荐入门）

获取真实 Polymarket 市场数据，模拟交易，零风险验证策略：

```bash
# 保守策略 + 终端仪表盘
python src/core/trade_runner.py --paper-trade --profile conservative --dashboard

# 激进策略 + Web 仪表盘
python src/core/trade_runner.py --paper-trade --profile aggressive --web --web-port 8186

# 同时启用终端和 Web 仪表盘
python src/core/trade_runner.py --paper-trade --dashboard --web
```

**输出示例**：
```
📊 PAPER TRADING MODE: 真实数据 + 模拟交易
✅ 获取Polymarket真实市场数据
✅ 运行真实交易逻辑
✅ 模拟买入和结算
✅ 跟踪盈亏和权益
❌ 不执行真实交易

📊 Market: Will BTC be above $65,000 in 5 minutes?
   UP: 0.723 | DOWN: 0.277

============================================================
Cycle: 10 | BTC: $65,123.45
Equity: $1,000.00 | PnL: $0.00 (0.0%)
Trades: 0 | Win Rate: 0.0%
Active Positions: 0
✅ SIGNAL: UP $12.50
   Win Prob: 0.723
   EV: 0.085
📝 PAPER BUY: UP $12.50 @ 0.723
```

#### 🎯 狙击模式（自动启用）

纸面交易模式下，狙击模式**自动启用**。在到期前最后 5 秒，如果满足极端条件（OBI > 0.7 且胜率 > 98%），会自动执行小额高胜率狙击交易：

```
🎯 SNIPER: UP $5.00 @ 0.980 (conf=0.95)
```

狙击参数可在 `config/btc_5m_profiles.yaml` 中调整：
```yaml
sniper_mode:
  enabled: true
  window_start_sec: 5      # 狙击窗口开始（秒）
  window_end_sec: 2        # 狙击窗口结束（秒）
  min_win_probability: 0.98  # 最低胜率要求
  min_obi: 0.7             # 最低OBI要求
  max_stake_usd: 10.0      # 最大下注金额
```

#### 🎮 模拟模式（离线测试）

完全离线，使用内置模拟数据：

```bash
# 正常市场
python src/core/trade_runner.py --simulator --scene normal

# 高波动市场
python src/core/trade_runner.py --simulator --scene volatile

# 崩盘场景
python src/core/trade_runner.py --simulator --scene crash

# 带仪表盘
python src/core/trade_runner.py --simulator --scene normal --dashboard
```

**可用场景**：
| 场景 | 描述 | 波动率 |
|------|------|--------|
| `normal` | 正常市场 | 2% |
| `trending` | 趋势市场（单边行情） | 3% |
| `volatile` | 高波动 | 5% |
| `crash` | 崩盘（快速下跌） | 8% |
| `pump` | 暴涨（快速上涨） | 8% |

#### 📡 真实数据模式

仅获取数据，不交易：

```bash
python src/core/trade_runner.py --real-data --profile conservative
```

#### 🚀 实盘交易模式（需要 API 密钥）

```bash
python src/core/trade_runner.py --execute --profile conservative
```

### 4. 命令行参数完整参考

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--config` | 配置文件路径 | `config/btc_5m_profiles.yaml` |
| `--profile` | 策略配置：`conservative` / `aggressive` | `conservative` |
| `--paper-trade` | 纸面交易模式（真实数据+模拟交易） | 关闭 |
| `--simulator` | 模拟数据模式（离线测试） | 关闭 |
| `--scene` | 模拟场景：`normal`/`trending`/`volatile`/`crash`/`pump` | `normal` |
| `--real-data` | 真实数据模式（仅获取） | 关闭 |
| `--execute` | 实盘交易（需要 API 密钥） | 关闭 |
| `--dry-run` | 仅观察不执行 | 关闭 |
| `--dashboard` | 启用终端 Rich 实时仪表盘 | 关闭 |
| `--web` | 启用 Web 浏览器仪表盘 | 关闭 |
| `--web-port` | Web 仪表盘端口 | `8186` |

## 📈 策略说明

### 核心策略：动量跟踪（Momentum into Close）

1. **交易标的**: Polymarket BTC 5分钟涨跌市场
2. **入场时机**: 到期前2-5分钟
3. **信号确认**:
   - BTC已移动$70-$100
   - 市场倾斜支持动量方向
   - GBM胜率 > 65%
   - EV > 0.05
4. **仓位管理**: 凯利公式（保守1/4）
5. **风控**: 每日最大亏损10%，连续亏损3次熔断

### 数学模型

| 模型 | 功能 | 参数 |
|------|------|------|
| GBM | 胜率预测 | mu=0.001, sigma=0.02 |
| OBI | 订单簿分析 | 阈值=0.35 |
| ATR | 动态阈值 | period=14, alpha=1.5 |
| EV | 期望值校验 | min_ev=0.05 |

### 风控参数

| 参数 | Conservative | Aggressive |
|------|--------------|------------|
| 最大仓位 | 5% | 15% |
| 凯利分数 | 1/4 | 1/2 |
| 每日最大亏损 | 10% | 20% |
| 连续亏损熔断 | 3次 | 5次 |
| 最大回撤 | 15% | 25% |

## 📊 纸面交易绩效指标

运行纸面交易后，退出时会显示：

```
============================================================
  📊 Paper Trading Performance Summary
============================================================
  Initial Equity:    $1,000.00
  Current Equity:    $1,045.23
  Total PnL:         $+45.23 (+4.52%)
  Total Trades:      25
  Winning Trades:    18
  Losing Trades:     7
  Win Rate:          72.0%
  Avg PnL/Trade:     $+1.81
  Max Drawdown:      3.2%
  Max Consec Losses: 2
============================================================
```

**优秀标准**：
- 胜率 > 60%
- 总盈亏 > 0
- 最大回撤 < 10%
- 最大连续亏损 < 5

## ⚙️ 配置文件

编辑 `config/btc_5m_profiles.yaml` 调整策略参数：

```yaml
models:
  gbm:
    min_win_probability: 0.65  # 最低胜率要求
  ev:
    min_ev: 0.05               # 最低期望值

profiles:
  conservative:
    sizing:
      max_position_pct: 5.0    # 最大仓位
      kelly_fraction_type: quarter
```

## 🛡️ 执行前检查清单

1. ✅ **市场有效性**: 确认BTC 5m市场活跃
2. ✅ **时间窗口**: 偏好到期前~120秒入场
3. ✅ **动量确认**: BTC移动有意义（$70-$100）
4. ✅ **倾斜确认**: 市场倾斜支持方向
5. ✅ **流动性**: 价差和深度满足要求
6. ✅ **仓位控制**: 验证仓位大小和每日亏损限制
7. ✅ **止损/退出**: 配置止损和退出时间
8. ✅ **执行模式**: 先dry-run验证，再--execute

## 🖥️ 实时仪表盘

系统提供两种仪表盘模式，可同时启用：

### 终端仪表盘（Rich）

```bash
python src/core/trade_runner.py --paper-trade --dashboard
```

基于 Rich 库的终端实时仪表盘，显示：
- BTC 实时价格走势图
- OBI / GBM / Polymarket 价格曲线
- 持仓和交易记录
- 策略信号和日志流
- 权益和盈亏统计

按 `Ctrl+C` 退出。

### Web 仪表盘

```bash
python src/core/trade_runner.py --paper-trade --web --web-port 8186
```

浏览器自动打开 `http://localhost:8186`，显示与终端仪表盘相同的数据，但更美观且支持移动端查看。

### 同时启用

```bash
python src/core/trade_runner.py --paper-trade --dashboard --web
```

## 📝 策略验证流程

1. **模拟测试** (第1天)
   ```bash
   python src/core/trade_runner.py --simulator --scene normal --dashboard
   ```
   - 确认所有模块正常加载
   - 观察信号生成逻辑

2. **纸面交易** (第1-2周)
   ```bash
   python src/core/trade_runner.py --paper-trade --dashboard
   ```
   - 验证策略在真实数据下的表现
   - 观察胜率和盈亏
   - 优化参数

3. **分析绩效** (第2-3周)
   - 检查 `data/logs/` 下的 CSV 日志
   - 计算夏普比率
   - 分析最大回撤

4. **小额实盘** (第3-4周)
   ```bash
   python src/core/trade_runner.py --execute --profile conservative
   ```

## ⚠️ 风险提示

本系统仅供教育和研究使用，不构成投资建议。

- 使用自己的风险限额
- 设置每日亏损上限
- 严格控制仓位
- 先用纸面交易验证策略

## 🤝 贡献

- Fork 本仓库
- 创建特性分支
- 提交更改
- 提交 PR 到 `main`

欢迎提交 PR！