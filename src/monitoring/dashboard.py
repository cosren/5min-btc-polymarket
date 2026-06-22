#!/usr/bin/env python3
"""实时终端仪表盘 v2.0

使用 Rich + Plotext 构建机构级交易监控面板

模块:
  1. 网络与系统健康状态区 - 延迟/心跳/余额
  2. BTC价格+OBI双Y轴折线图 - 价格与订单簿不平衡
  3. 实时交易日志流 - 信号/成交/风控警报
  4. GBM胜率 vs 市场概率对比图
  5. 今日胜率仪表盘
  6. 每小时/每日PNL柱状图
  7. 策略分类统计表 - OBI阈值分档表现
"""
import time
import threading
from typing import Optional, Dict, List, Any
from collections import deque
from dataclasses import dataclass, field

try:
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.text import Text
    from rich.console import Console
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

try:
    import plotext as plt
    PLOTEXT_AVAILABLE = True
except ImportError:
    PLOTEXT_AVAILABLE = False


# ============================================================
# 数据状态
# ============================================================

@dataclass
class DashboardState:
    """仪表盘全局状态"""
    # 网络延迟
    poly_latency_ms: float = 0.0
    binance_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    latencies: deque = field(default_factory=lambda: deque(maxlen=30))

    # 心跳
    heartbeat: str = "RUNNING"
    ws_connected: bool = False

    # 余额
    equity: float = 1000.0
    initial_equity: float = 1000.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    daily_pnl: float = 0.0
    active_position_side: str = ""
    active_position_stake: float = 0.0
    active_position_entry: float = 0.0

    # BTC 价格
    btc_price: float = 0.0
    btc_change_pct: float = 0.0
    btc_history: deque = field(default_factory=lambda: deque(maxlen=120))
    btc_high: float = 0.0
    btc_low: float = float('inf')

    # OBI 历史
    obi_history: deque = field(default_factory=lambda: deque(maxlen=120))

    # Polymarket
    market_question: str = ""
    up_price: float = 0.0
    down_price: float = 0.0
    poly_price_history: deque = field(default_factory=lambda: deque(maxlen=120))

    # 决策引擎
    gbm_win_prob: float = 0.0
    gbm_history: deque = field(default_factory=lambda: deque(maxlen=120))
    ev: float = 0.0
    obi: float = 0.0
    kelly_fraction: float = 0.0
    signal_side: str = ""
    signal_stake: float = 0.0
    should_trade: bool = False
    filter_reason: str = ""
    combined_signal: float = 0.0

    # 统计
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    cycle_count: int = 0
    time_to_expiry: float = 300.0

    # 仓位与交易记录
    active_positions: List[Dict] = field(default_factory=list)
    recent_trades: List[Dict] = field(default_factory=list)

    # 历史 PnL
    hourly_pnl: Dict[str, float] = field(default_factory=dict)

    # OBI 策略分档
    obi_strategy_stats: Dict[str, Dict] = field(default_factory=dict)

    # 日志流
    log_entries: deque = field(default_factory=lambda: deque(maxlen=100))


# ============================================================
# 辅助函数
# ============================================================

def _latency_color(ms: float) -> str:
    if ms <= 0:
        return "dim"
    if ms < 100:
        return "green"
    if ms < 300:
        return "yellow"
    return "red"


def _latency_icon(ms: float) -> str:
    if ms <= 0:
        return "⚪"
    if ms < 100:
        return "🟢"
    if ms < 300:
        return "🟡"
    return "🔴"


def _pnl_color(val: float) -> str:
    if val > 0:
        return "green"
    if val < 0:
        return "red"
    return "dim"


def _pnl_text(val: float) -> str:
    if val > 0:
        return f"+${val:,.2f}"
    if val < 0:
        return f"-${abs(val):,.2f}"
    return f"${val:,.2f}"


def _render_gauge(pct: float, width: int = 30) -> str:
    """渲染 ASCII 仪表盘"""
    pct = max(0, min(1, pct))
    filled = int(pct * width)
    if pct >= 0.6:
        color = "green"
    elif pct >= 0.4:
        color = "yellow"
    else:
        color = "red"
    bar = f"[{color}]{'█' * filled}[/{color}]{'░' * (width - filled)}"
    return f"[{color}]{pct:.1%}[/{color}]  {bar}"


def _spark(values: list, width: int = 40) -> str:
    """ASCII 走势图"""
    if not values or len(values) < 2:
        return "─" * width
    chars = " ▁▂▃▄▅▆▇█"
    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        return "▄" * width
    step = max(len(values) // width, 1)
    sampled = [values[i] for i in range(0, len(values), step)][:width]
    return "".join(chars[min(int((v - vmin) / (vmax - vmin) * 7), 7)] for v in sampled)


# ============================================================
# 仪表盘主类
# ============================================================

class TradingDashboard:
    """机构级实时交易仪表盘"""

    def __init__(self):
        if not RICH_AVAILABLE:
            raise ImportError("请安装 rich: pip install rich")
        if not PLOTEXT_AVAILABLE:
            raise ImportError("请安装 plotext: pip install plotext")
        self.console = Console()
        self.state = DashboardState()
        self._lock = threading.Lock()
        self._running = False

    def update(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.state, key):
                    setattr(self.state, key, value)

    def add_log(self, level: str, message: str):
        """添加日志条目"""
        with self._lock:
            timestamp = time.strftime("%H:%M:%S")
            self.state.log_entries.append({
                "time": timestamp,
                "level": level,
                "message": message
            })

    # --------------------------------------------------------
    # 1. 网络与系统健康状态区
    # --------------------------------------------------------
    def _build_health_panel(self) -> Panel:
        s = self.state
        content = Text()

        # 延迟行
        content.append(f" {_latency_icon(s.binance_latency_ms)} Binance: ", style="dim")
        content.append(f"{s.binance_latency_ms:.0f}ms", style=_latency_color(s.binance_latency_ms))
        content.append("  |  ")
        content.append(f"{_latency_icon(s.poly_latency_ms)} Polymarket: ", style="dim")
        content.append(f"{s.poly_latency_ms:.0f}ms", style=_latency_color(s.poly_latency_ms))
        content.append("  |  ")

        # 心跳
        hb_color = "green" if s.heartbeat == "RUNNING" else "red"
        content.append(f"💓 Heartbeat: ", style="dim")
        content.append(f"{s.heartbeat}", style=f"bold {hb_color}")

        # 余额行
        content.append(f"\n 💰 Equity: ", style="dim")
        content.append(f"${s.equity:,.2f}", style="bold white")
        content.append(f"  |  PnL: ")
        content.append(_pnl_text(s.total_pnl), style=_pnl_color(s.total_pnl))
        content.append(f"  |  Daily: ")
        content.append(_pnl_text(s.daily_pnl), style=_pnl_color(s.daily_pnl))

        ws_color = "green" if s.ws_connected else "red"
        content.append(f"  |  WS: ", style="dim")
        content.append("🟢" if s.ws_connected else "🔴", style=ws_color)

        return Panel(content, title="[bold cyan]🌐 Network & System Health[/bold cyan]",
                     border_style="cyan", height=4)

    # --------------------------------------------------------
    # 2. BTC价格 + OBI 双Y轴折线图
    # --------------------------------------------------------
    def _build_price_obi_chart(self) -> Panel:
        s = self.state
        btc = list(s.btc_history)
        obi = list(s.obi_history)
        content = Text()

        if len(btc) >= 2:
            latest = btc[-1]
            prev = btc[-2]
            change = latest - prev
            color = "green" if change >= 0 else "red"
            sign = "+" if change >= 0 else ""
            content.append(f" BTC: ", style="dim")
            content.append(f"${latest:,.2f}", style="bold white")
            content.append(f"  {sign}{change:+,.2f}", style=f"bold {color}")
            content.append(f"\n {_spark(btc)}\n", style="cyan")
        else:
            content.append(" BTC: Waiting...\n\n", style="dim")

        if len(obi) >= 2:
            latest_obi = obi[-1]
            obi_color = "green" if latest_obi > 0.15 else "red" if latest_obi < -0.15 else "yellow"
            content.append(f" OBI: ", style="dim")
            content.append(f"{latest_obi:+.3f}", style=f"bold {obi_color}")
            content.append(f"\n {_spark(obi)}", style="yellow")
        else:
            content.append(" OBI: Waiting...", style="dim")

        return Panel(content, title="[bold yellow]📈 BTC Price & OBI[/bold yellow]",
                     border_style="yellow")
    # 3. 实时交易日志流
    # --------------------------------------------------------
    def _build_log_stream(self) -> Panel:
        s = self.state
        entries = list(s.log_entries)
        if not entries:
            entries = [{"time": "--:--:--", "level": "INFO", "message": "等待交易信号..."}]

        # 显示最近 18 条
        recent = entries[-18:]
        lines = []
        for e in recent:
            t = e["time"]
            lvl = e["level"]
            msg = e["message"]

            if lvl == "TRADE":
                color = "bold green"
                prefix = "💰"
            elif lvl == "WARN":
                color = "bold yellow"
                prefix = "⚠️"
            elif lvl == "ERROR":
                color = "bold red"
                prefix = "🚨"
            else:
                color = "dim"
                prefix = "·"

            # 截断过长消息
            if len(msg) > 70:
                msg = msg[:67] + "..."

            lines.append(f"[{color}][{t}] {prefix} {msg}[/{color}]")

        content = Text("\n".join(lines))
        return Panel(content, title="[bold magenta]📋 Trade Log Stream[/bold magenta]",
                     border_style="magenta")

    # --------------------------------------------------------
    # 4. GBM胜率 vs 市场概率对比图
    # --------------------------------------------------------
    def _build_probability_chart(self) -> Panel:
        s = self.state
        gbm = list(s.gbm_history)
        poly_prices = list(s.poly_price_history)
        content = Text()

        if len(gbm) >= 2:
            latest_gbm = gbm[-1]
            gbm_color = "green" if latest_gbm >= 0.65 else "yellow" if latest_gbm >= 0.50 else "red"
            content.append(f" GBM: ", style="dim")
            content.append(f"{latest_gbm:.3f}", style=f"bold {gbm_color}")
            content.append(f"\n {_spark(gbm)}\n", style="cyan")
        else:
            content.append(" GBM: Waiting...\n\n", style="dim")

        if len(poly_prices) >= 2:
            latest_poly = poly_prices[-1]
            content.append(f" Poly: ", style="dim")
            content.append(f"{latest_poly:.3f}", style="bold magenta")
            content.append(f"\n {_spark(poly_prices)}", style="magenta")
        else:
            content.append(" Poly: Waiting...", style="dim")

        return Panel(content, title="[bold blue]🎯 GBM WinProb vs Poly Price[/bold blue]",
                     border_style="blue")

    # --------------------------------------------------------
    # 5. 今日胜率仪表盘
    # --------------------------------------------------------
    def _build_win_gauge(self) -> Panel:
        s = self.state
        content = Text()

        content.append(f"  Win Rate: {_render_gauge(s.win_rate, 30)}\n\n")
        content.append(f"  Trades: {s.total_trades}", style="dim")
        content.append(f"  |  Current OBI: {s.obi:+.3f}\n", style="dim")
        content.append(f"  GBM: {s.gbm_win_prob:.3f}", style="dim")
        content.append(f"  |  EV: {s.ev:+.3f}", style="dim")
        content.append(f"  |  Kelly: {s.kelly_fraction:.1%}\n", style="dim")

        if s.should_trade:
            content.append(f"  Signal: ✅ {s.signal_side} ${s.signal_stake:,.2f}", style="bold green")
        else:
            content.append(f"  Signal: ❌ {s.filter_reason}", style="bold red")

        time_left = max(0, s.time_to_expiry)
        content.append(f"\n  ⏱️ Expiry: {time_left:.0f}s", style="dim")

        return Panel(content, title="[bold green]📊 Win Rate & Signal[/bold green]",
                     border_style="green")

    # --------------------------------------------------------
    # 6. PnL 柱状图
    # --------------------------------------------------------
    def _build_pnl_chart(self) -> Panel:
        s = self.state
        hourly = s.hourly_pnl
        if not hourly:
            return Panel("[dim]No PnL history yet[/dim]",
                         title="[bold red]📉 Hourly PnL[/bold red]",
                         border_style="red")

        keys = sorted(hourly.keys())[-12:]
        values = [hourly[k] for k in keys]
        content = Text()

        if values:
            total = sum(values)
            pnl_color = "green" if total >= 0 else "red"
            content.append(f" Sum: ", style="dim")
            content.append(_pnl_text(total), style=f"bold {pnl_color}")
            content.append(f"\n {_spark(values)}\n", style=pnl_color)

        return Panel(content, title="[bold red]📉 Hourly PnL[/bold red]",
                     border_style="red")

    # --------------------------------------------------------
    # 7. 策略分类统计表
    # --------------------------------------------------------
    def _build_strategy_table(self) -> Panel:
        s = self.state
        table = Table(box=box.SIMPLE, header_style="bold cyan", border_style="dim")
        table.add_column("OBI Range", style="dim", width=14)
        table.add_column("Trades", justify="right", width=8)
        table.add_column("Wins", justify="right", width=8)
        table.add_column("Win Rate", justify="right", width=10)
        table.add_column("Net PnL", justify="right", width=12)
        table.add_column("Avg PnL", justify="right", width=12)

        if not s.obi_strategy_stats:
            table.add_row("0.00-0.15", "0", "0", "0.0%", "$0.00", "$0.00")
            table.add_row("0.15-0.25", "0", "0", "0.0%", "$0.00", "$0.00")
            table.add_row("0.25-0.35", "0", "0", "0.0%", "$0.00", "$0.00")
            table.add_row(">0.35", "0", "0", "0.0%", "$0.00", "$0.00")
        else:
            for label, stats in s.obi_strategy_stats.items():
                wr = stats.get("wins", 0) / stats.get("trades", 1) if stats.get("trades", 0) > 0 else 0
                wr_color = "green" if wr >= 0.5 else "red"
                pnl_color = "green" if stats.get("net_pnl", 0) >= 0 else "red"
                table.add_row(
                    label,
                    str(stats.get("trades", 0)),
                    str(stats.get("wins", 0)),
                    Text(f"{wr:.1%}", style=wr_color),
                    Text(f"${stats.get('net_pnl', 0):+,.2f}", style=pnl_color),
                    Text(f"${stats.get('avg_pnl', 0):+,.2f}", style=pnl_color),
                )

        return Panel(table, title="[bold white]📊 Strategy Breakdown by OBI Range[/bold white]",
                     border_style="white")

    # --------------------------------------------------------
    # 8. 仓位与交易明细
    # --------------------------------------------------------
    def _build_portfolio_panel(self) -> Panel:
        s = self.state
        content = Text()

        active_count = len(s.active_positions)
        in_play = sum(p.get('stake_usd', 0) for p in s.active_positions)
        available = s.equity
        content.append(f" 📊 Active: ", style="dim")
        content.append(f"{active_count}", style="bold yellow")
        content.append(f"  |  💸 In Play: ", style="dim")
        content.append(f"${in_play:,.2f}", style="bold yellow")
        content.append(f"  |  🏦 Available: ", style="dim")
        content.append(f"${available:,.2f}", style="bold white")

        if s.active_positions:
            content.append("\n")
            for p in s.active_positions[:3]:
                side_color = "green" if p.get('side') == 'UP' else "red"
                content.append(f"   ┣ {p.get('side',''):4s} ", style=f"bold {side_color}")
                content.append(f"${p.get('stake_usd',0):,.2f}", style="dim")
                content.append(f" @ {p.get('entry_price',0):.3f}", style="dim")
                content.append(f"  → {p.get('market_slug','')[:20]}", style="dim")
                content.append("\n")
        else:
            content.append("\n   (no active positions)\n", style="dim")

        content.append(f"\n ── Recent Trades ──", style="bold dim")
        trades = s.recent_trades[-8:] if s.recent_trades else []
        if not trades:
            content.append("\n   (no trades yet)", style="dim")
        else:
            for t in trades:
                is_win = t.get('is_win', False)
                icon = "✅" if is_win else "❌"
                pnl = t.get('pnl_usd', 0)
                pnl_pct = t.get('pnl_pct', 0)
                content.append(f"\n   {icon} {t.get('side',''):4s} ", style="")
                content.append(f"${t.get('stake_usd',0):,.2f}", style="dim")
                content.append(f" → ${t.get('stake_usd',0)+pnl:,.2f} ", style="")
                content.append(_pnl_text(pnl), style=_pnl_color(pnl))
                content.append(f" ({pnl_pct:+.1f}%)", style=_pnl_color(pnl))
                content.append(f"  {t.get('time','')}", style="dim")

        content.append(f"\n ── Summary ──", style="bold dim")
        content.append(f"\n Trades: {s.total_trades}", style="dim")
        content.append(f"  |  W: {s.winning_trades}", style="green")
        content.append(f"  /  L: {s.losing_trades}", style="red")
        content.append(f"  |  WR: {s.win_rate:.1%}", style="bold white")
        content.append(f"  |  Net: ")
        content.append(_pnl_text(s.total_pnl), style=_pnl_color(s.total_pnl))

        return Panel(content, title="[bold magenta]💼 Portfolio & Recent Trades[/bold magenta]",
                     border_style="magenta")

    # --------------------------------------------------------
    # 布局
    # --------------------------------------------------------
    def _build_layout(self) -> Layout:
        layout = Layout()

        layout.split(
            Layout(name="health", size=4),
            Layout(name="portfolio", size=9),
            Layout(name="charts_top", size=8),
            Layout(name="charts_mid", size=8),
            Layout(name="charts_bottom", size=6),
            Layout(name="strategy_table", size=6),
        )

        layout["charts_top"].split_row(
            Layout(self._build_price_obi_chart(), name="price_obi"),
            Layout(self._build_log_stream(), name="log"),
        )

        layout["charts_mid"].split_row(
            Layout(self._build_probability_chart(), name="prob"),
            Layout(self._build_win_gauge(), name="gauge"),
        )

        layout["charts_bottom"].update(self._build_pnl_chart())
        layout["health"].update(self._build_health_panel())
        layout["portfolio"].update(self._build_portfolio_panel())
        layout["strategy_table"].update(self._build_strategy_table())

        return layout

    def run(self):
        self._running = True
        with Live(self._build_layout(), console=self.console, refresh_per_second=4, screen=True) as live:
            while self._running:
                with self._lock:
                    live.update(self._build_layout())
                time.sleep(0.25)

    def stop(self):
        self._running = False

    def start_in_thread(self) -> threading.Thread:
        t = threading.Thread(target=self.run, daemon=True)
        t.start()
        return t