#!/usr/bin/env python3
"""
Web 仪表盘 — 在浏览器中展示实时交易数据
使用 Python 内置 http.server，无需额外依赖
"""

import json
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import deque


# ============================================================
# 完整的 HTML 仪表盘（单文件，无外部依赖）
# ============================================================

WEB_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BTC 5m Trading Dashboard</title>
<style>
  :root {
    --bg: #0a0e14;
    --panel-bg: #12171f;
    --border: #2a3a4a;
    --text: #c8d6e5;
    --dim: #5a6a7a;
    --green: #00d68f;
    --red: #ff6b6b;
    --yellow: #ffd93d;
    --cyan: #00b4d8;
    --magenta: #c084fc;
    --white: #f0f0f0;
    --font: 'SF Mono', 'Fira Code', 'Consolas', 'Monaco', monospace;
    --chart-green: #00d68f;
    --chart-red: #ff6b6b;
    --chart-yellow: #ffd93d;
    --chart-cyan: #00b4d8;
    --chart-magenta: #c084fc;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 13px;
    line-height: 1.5;
    padding: 12px;
    min-height: 100vh;
  }

  .header {
    text-align: center;
    padding: 8px 0 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 12px;
  }
  .header h1 { font-size: 18px; color: var(--cyan); letter-spacing: 2px; }
  .header .sub { font-size: 11px; color: var(--dim); margin-top: 4px; }

  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .full { grid-column: 1 / -1; }

  .panel {
    background: var(--panel-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
    overflow: hidden;
  }

  .panel-title {
    font-size: 12px;
    font-weight: bold;
    color: var(--cyan);
    margin-bottom: 8px;
    letter-spacing: 1px;
    text-transform: uppercase;
  }
  .panel-title.magenta { color: var(--magenta); }
  .panel-title.green { color: var(--green); }
  .panel-title.yellow { color: var(--yellow); }
  .panel-title.red { color: var(--red); }

  /* Health */
  .health-row {
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
    align-items: center;
  }
  .health-item { display: flex; align-items: center; gap: 6px; }
  .health-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .dot-green { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .dot-yellow { background: var(--yellow); box-shadow: 0 0 6px var(--yellow); }
  .dot-red { background: var(--red); box-shadow: 0 0 6px var(--red); }
  .dot-gray { background: #555; }

  .label { color: var(--dim); }
  .value { font-weight: bold; }
  .value.green { color: var(--green); }
  .value.red { color: var(--red); }
  .value.yellow { color: var(--yellow); }
  .value.white { color: var(--white); }
  .value.cyan { color: var(--cyan); }

  /* Portfolio */
  .portfolio-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16px;
  }
  .pos-card {
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 8px;
  }
  .trade-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 0;
    border-bottom: 1px solid #1a2230;
  }
  .trade-row:last-child { border-bottom: none; }
  .badge {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: bold;
  }
  .badge-up { background: rgba(0,214,143,0.15); color: var(--green); }
  .badge-down { background: rgba(255,107,107,0.15); color: var(--red); }
  .badge-win { background: rgba(0,214,143,0.15); color: var(--green); }
  .badge-loss { background: rgba(255,107,107,0.15); color: var(--red); }

  /* Charts */
  .chart-container { width: 100%; height: 150px; }
  .chart-container.small { height: 100px; }
  .chart-container svg { width: 100%; height: 100%; }

  /* Signal */
  .signal-box {
    padding: 10px 14px;
    border-radius: 4px;
    text-align: center;
    font-size: 14px;
    font-weight: bold;
  }
  .signal-buy { background: rgba(0,214,143,0.1); border: 1px solid var(--green); color: var(--green); }
  .signal-sell { background: rgba(255,107,107,0.1); border: 1px solid var(--red); color: var(--red); }
  .signal-none { background: rgba(90,106,122,0.1); border: 1px solid var(--dim); color: var(--dim); }

  .signal-metrics {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    margin-top: 8px;
  }

  /* Gauge */
  .gauge-bar {
    height: 20px;
    background: #1a2230;
    border-radius: 10px;
    overflow: hidden;
    margin: 8px 0;
  }
  .gauge-fill {
    height: 100%;
    border-radius: 10px;
    transition: width 0.5s;
  }
  .gauge-fill.good { background: linear-gradient(90deg, #00d68f, #00e676); }
  .gauge-fill.warn { background: linear-gradient(90deg, #ffd93d, #ffab00); }
  .gauge-fill.bad { background: linear-gradient(90deg, #ff6b6b, #ff1744); }

  /* Log */
  .log-stream {
    max-height: 200px;
    overflow-y: auto;
    font-size: 11px;
  }
  .log-entry { padding: 2px 0; display: flex; gap: 8px; }
  .log-time { color: var(--dim); min-width: 60px; }
  .log-msg { flex: 1; }
  .log-msg.trade { color: var(--green); }
  .log-msg.warn { color: var(--yellow); }
  .log-msg.error { color: var(--red); }

  .spacer { flex: 1; }
  .flex-row { display: flex; align-items: center; gap: 12px; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  .pulse { animation: pulse 2s infinite; }

  .updated { font-size: 10px; color: var(--dim); text-align: right; margin-top: 6px; }
</style>
</head>
<body>

<div class="header">
  <h1>₿ BTC 5-Minute Trading Dashboard</h1>
  <div class="sub">Paper Trading Mode · Real-time Polymarket Data</div>
</div>

<div class="grid">
  <!-- Health Panel -->
  <div class="panel full">
    <div class="panel-title">🌐 Network & System Health</div>
    <div class="health-row">
      <div class="health-item">
        <span class="health-dot" id="dot-binance"></span>
        <span class="label">Binance:</span>
        <span class="value" id="val-binance">--</span>
      </div>
      <div class="health-item">
        <span class="health-dot" id="dot-poly"></span>
        <span class="label">Polymarket:</span>
        <span class="value" id="val-poly">--</span>
      </div>
      <div class="health-item">
        <span class="label">💓 Heartbeat:</span>
        <span class="value green pulse" id="val-heartbeat">RUNNING</span>
      </div>
      <div class="spacer"></div>
      <div class="health-item">
        <span class="label">💰 Equity:</span>
        <span class="value white" id="val-equity">$1,000.00</span>
      </div>
      <div class="health-item">
        <span class="label">PnL:</span>
        <span class="value" id="val-pnl">$0.00</span>
      </div>
      <div class="health-item">
        <span class="label">Daily:</span>
        <span class="value" id="val-daily-pnl">$0.00</span>
      </div>
    </div>
  </div>

  <!-- BTC Price Chart -->
  <div class="panel">
    <div class="panel-title yellow">📈 BTC Price</div>
    <div class="flex-row">
      <span class="value white" style="font-size:20px;" id="val-btc-price">--</span>
      <span class="value" style="font-size:14px;" id="val-btc-change">--</span>
    </div>
    <div class="chart-container" id="chart-btc"></div>
  </div>

  <!-- OBI Chart -->
  <div class="panel">
    <div class="panel-title yellow">📊 Order Book Imbalance (OBI)</div>
    <div class="flex-row">
      <span class="value" style="font-size:16px;" id="val-obi">--</span>
    </div>
    <div class="chart-container" id="chart-obi"></div>
  </div>

  <!-- GBM vs Poly Chart -->
  <div class="panel">
    <div class="panel-title cyan">🎯 GBM WinProb vs Poly Price</div>
    <div class="chart-container" id="chart-gbm"></div>
  </div>

  <!-- Signal & Win Rate -->
  <div class="panel">
    <div class="panel-title green">📊 Signal & Win Rate</div>
    <div class="signal-box signal-none" id="signal-box">⏳ Waiting for signal...</div>
    <div class="signal-metrics">
      <div><span class="label">GBM:</span> <span class="value" id="val-gbm">--</span></div>
      <div><span class="label">EV:</span> <span class="value" id="val-ev">--</span></div>
      <div><span class="label">Kelly:</span> <span class="value" id="val-kelly">--</span></div>
      <div><span class="label">OBI:</span> <span class="value" id="val-obi2">--</span></div>
    </div>
    <div style="margin-top:8px;">
      <span class="label">Win Rate:</span>
      <span class="value white" id="val-winrate">0.0%</span>
      <div class="gauge-bar"><div class="gauge-fill bad" id="gauge-winrate" style="width:0%"></div></div>
    </div>
    <div>
      <span class="label">Trades: </span><span class="value" id="val-trades">0</span>
      <span class="label"> | W: </span><span class="value green" id="val-wins">0</span>
      <span class="label"> / L: </span><span class="value red" id="val-losses">0</span>
      <span class="label"> | ⏱️ Expiry: </span><span class="value" id="val-expiry">300s</span>
    </div>
  </div>

  <!-- PnL Chart -->
  <div class="panel full">
    <div class="panel-title red">📉 Cumulative PnL</div>
    <div class="chart-container small" id="chart-pnl"></div>
    <div class="flex-row" style="margin-top:8px;">
      <span class="label">Net: </span><span class="value" id="val-net-pnl" style="font-size:18px;">$0.00</span>
    </div>
  </div>

  <!-- Portfolio -->
  <div class="panel full">
    <div class="panel-title magenta">💼 Portfolio & Recent Trades</div>
    <div class="portfolio-grid">
      <div class="pos-card">
        <div class="label">Active Positions</div>
        <div id="active-positions" style="margin-top:6px; font-size:11px; color:var(--dim);">(none)</div>
      </div>
      <div class="pos-card">
        <div class="label">Recent Trades</div>
        <div id="recent-trades" style="margin-top:6px; font-size:11px; color:var(--dim);">(none)</div>
      </div>
      <div class="pos-card">
        <div class="label">Summary</div>
        <div style="margin-top:6px; font-size:11px;">
          <span id="summary-active">Active: 0</span><br>
          <span id="summary-inplay">In Play: $0.00</span><br>
          <span id="summary-available">Available: $1,000.00</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Trade Log -->
  <div class="panel full">
    <div class="panel-title magenta">📋 Trade Log</div>
    <div class="log-stream" id="log-stream">
      <div class="log-entry"><span class="log-time">--:--:--</span><span class="log-msg">等待交易信号...</span></div>
    </div>
  </div>
</div>

<div class="updated" id="last-updated">Last updated: --</div>

<script>
// ============================================================
// SVG Sparkline 渲染
// ============================================================
function renderSparkline(containerId, data, options = {}) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!data || data.length < 2) {
    container.innerHTML = '<div style="color:var(--dim);text-align:center;padding-top:50px;">Waiting for data...</div>';
    return;
  }

  const { color = '#00d68f', fillOpacity = 0.1, hlines = [], lineWidth = 1.5 } = options;
  const w = container.clientWidth || 500;
  const h = container.clientHeight || 150;
  const pad = { top: 10, right: 5, bottom: 20, left: 5 };
  const pw = w - pad.left - pad.right;
  const ph = h - pad.top - pad.bottom;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data.map((v, i) => {
    const x = pad.left + (i / (data.length - 1)) * pw;
    const y = pad.top + ph - ((v - min) / range) * ph;
    return `${x},${y}`;
  });

  // 填充区域
  const fillPoints = `${pad.left},${pad.top + ph} ` + points.join(' ') + ` ${pad.left + pw},${pad.top + ph}`;

  let svg = `<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">`;
  svg += `<defs><linearGradient id="g-${containerId}" x1="0" y1="0" x2="0" y2="1">`;
  svg += `<stop offset="0%" stop-color="${color}" stop-opacity="${fillOpacity + 0.1}"/>`;
  svg += `<stop offset="100%" stop-color="${color}" stop-opacity="0"/>`;
  svg += `</linearGradient></defs>`;

  // 水平参考线
  hlines.forEach(hl => {
    const y = pad.top + ph - ((hl.value - min) / range) * ph;
    svg += `<line x1="${pad.left}" y1="${y}" x2="${pad.left + pw}" y2="${y}" stroke="${hl.color || '#555'}" stroke-width="0.5" stroke-dasharray="4,4"/>`;
  });

  // 填充
  svg += `<polygon points="${fillPoints}" fill="url(#g-${containerId})"/>`;
  // 折线
  svg += `<polyline points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="${lineWidth}" stroke-linejoin="round"/>`;

  // 当前值标注
  const lastVal = data[data.length - 1];
  const lastY = pad.top + ph - ((lastVal - min) / range) * ph;
  svg += `<circle cx="${pad.left + pw}" cy="${lastY}" r="3" fill="${color}"/>`;

  svg += `</svg>`;
  container.innerHTML = svg;
}

// ============================================================
// 延迟颜色
// ============================================================
function latencyColor(ms) {
  if (ms <= 0) return 'gray';
  if (ms < 100) return 'green';
  if (ms < 300) return 'yellow';
  return 'red';
}

function latencyDotClass(ms) {
  if (ms <= 0) return 'dot-gray';
  if (ms < 100) return 'dot-green';
  if (ms < 300) return 'dot-yellow';
  return 'dot-red';
}

// ============================================================
// PnL 颜色
// ============================================================
function pnlColor(val) {
  if (val > 0) return 'green';
  if (val < 0) return 'red';
  return '';
}

function pnlText(val) {
  if (val > 0) return '+$' + val.toFixed(2);
  if (val < 0) return '-$' + Math.abs(val).toFixed(2);
  return '$' + val.toFixed(2);
}

// ============================================================
// 数据拉取 & 更新
// ============================================================
let logCount = 0;

async function fetchState() {
  try {
    const resp = await fetch('/api/state');
    const s = await resp.json();

    // --- Health ---
    document.getElementById('val-binance').textContent = (s.binance_latency_ms || 0).toFixed(0) + 'ms';
    document.getElementById('val-binance').className = 'value ' + latencyColor(s.binance_latency_ms || 0);
    document.getElementById('dot-binance').className = 'health-dot ' + latencyDotClass(s.binance_latency_ms || 0);

    document.getElementById('val-poly').textContent = (s.poly_latency_ms || 0).toFixed(0) + 'ms';
    document.getElementById('val-poly').className = 'value ' + latencyColor(s.poly_latency_ms || 0);
    document.getElementById('dot-poly').className = 'health-dot ' + latencyDotClass(s.poly_latency_ms || 0);

    document.getElementById('val-heartbeat').textContent = s.heartbeat || 'RUNNING';

    document.getElementById('val-equity').textContent = '$' + ((s.equity || 1000)).toFixed(2);
    document.getElementById('val-pnl').textContent = pnlText(s.total_pnl || 0);
    document.getElementById('val-pnl').className = 'value ' + pnlColor(s.total_pnl || 0);
    document.getElementById('val-daily-pnl').textContent = pnlText(s.daily_pnl || 0);
    document.getElementById('val-daily-pnl').className = 'value ' + pnlColor(s.daily_pnl || 0);

    // --- BTC Price ---
    const btc = s.btc_price || 0;
    document.getElementById('val-btc-price').textContent = '$' + btc.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    const changePct = s.btc_change_pct || 0;
    const changeEl = document.getElementById('val-btc-change');
    changeEl.textContent = (changePct >= 0 ? '+' : '') + changePct.toFixed(2) + '%';
    changeEl.className = 'value ' + (changePct >= 0 ? 'green' : 'red');

    if (s.btc_history && s.btc_history.length > 1) {
      renderSparkline('chart-btc', s.btc_history, {
        color: (s.btc_history[s.btc_history.length-1] >= s.btc_history[0]) ? '#00d68f' : '#ff6b6b',
        fillOpacity: 0.15
      });
    }

    // --- OBI ---
    const obi = s.obi || 0;
    document.getElementById('val-obi').textContent = 'OBI: ' + (obi >= 0 ? '+' : '') + obi.toFixed(3);
    document.getElementById('val-obi').className = 'value ' + (Math.abs(obi) > 0.3 ? (obi > 0 ? 'green' : 'red') : '');
    document.getElementById('val-obi2').textContent = (obi >= 0 ? '+' : '') + obi.toFixed(3);

    if (s.obi_history && s.obi_history.length > 1) {
      renderSparkline('chart-obi', s.obi_history, {
        color: '#ffd93d',
        fillOpacity: 0.1,
        hlines: [{value: 0.30, color: '#00d68f'}, {value: -0.30, color: '#ff6b6b'}, {value: 0, color: '#555'}]
      });
    }

    // --- GBM ---
    const gbm = s.gbm_win_prob || 0;
    document.getElementById('val-gbm').textContent = gbm.toFixed(3);
    document.getElementById('val-ev').textContent = (s.ev >= 0 ? '+' : '') + (s.ev || 0).toFixed(3);
    document.getElementById('val-kelly').textContent = ((s.kelly_fraction || 0) * 100).toFixed(1) + '%';

    if (s.gbm_history && s.poly_price_history) {
      const gbmData = s.gbm_history.length > 1 ? s.gbm_history : null;
      const polyData = s.poly_price_history.length > 1 ? s.poly_price_history : null;
      if (gbmData || polyData) {
        renderDualChart('chart-gbm', gbmData, polyData);
      }
    }

    // --- Signal ---
    const signalBox = document.getElementById('signal-box');
    if (s.should_trade) {
      signalBox.className = 'signal-box ' + (s.signal_side === 'UP' ? 'signal-buy' : 'signal-sell');
      signalBox.textContent = '✅ ' + s.signal_side + ' $' + (s.signal_stake || 0).toFixed(2);
    } else {
      signalBox.className = 'signal-box signal-none';
      signalBox.textContent = '❌ ' + (s.filter_reason || 'No signal');
    }

    // --- Win Rate ---
    const wr = s.win_rate || 0;
    document.getElementById('val-winrate').textContent = (wr * 100).toFixed(1) + '%';
    const gauge = document.getElementById('gauge-winrate');
    gauge.style.width = (wr * 100).toFixed(0) + '%';
    gauge.className = 'gauge-fill ' + (wr >= 0.6 ? 'good' : wr >= 0.4 ? 'warn' : 'bad');

    document.getElementById('val-trades').textContent = s.total_trades || 0;
    document.getElementById('val-wins').textContent = s.winning_trades || 0;
    document.getElementById('val-losses').textContent = s.losing_trades || 0;
    document.getElementById('val-expiry').textContent = ((s.time_to_expiry || 300)).toFixed(0) + 's';

    // --- Net PnL ---
    document.getElementById('val-net-pnl').textContent = pnlText(s.total_pnl || 0);
    document.getElementById('val-net-pnl').className = 'value ' + pnlColor(s.total_pnl || 0);

    // --- PnL chart ---
    if (s.hourly_pnl) {
      const keys = Object.keys(s.hourly_pnl).sort();
      const vals = keys.map(k => s.hourly_pnl[k]);
      if (vals.length > 1) {
        renderSparkline('chart-pnl', vals, {
          color: (vals[vals.length-1] >= 0) ? '#00d68f' : '#ff6b6b',
          fillOpacity: 0.15
        });
      }
    }

    // --- Portfolio ---
    const ap = s.active_positions || [];
    const apDiv = document.getElementById('active-positions');
    if (ap.length === 0) {
      apDiv.innerHTML = '<span style="color:var(--dim);">(no active positions)</span>';
    } else {
      apDiv.innerHTML = ap.map(p => {
        const cls = p.side === 'UP' ? 'badge-up' : 'badge-down';
        return `<div style="margin-bottom:4px;"><span class="badge ${cls}">${p.side}</span> $${(p.stake_usd || 0).toFixed(2)} @ ${(p.entry_price || 0).toFixed(3)}</div>`;
      }).join('');
    }

    const rt = s.recent_trades || [];
    const rtDiv = document.getElementById('recent-trades');
    if (rt.length === 0) {
      rtDiv.innerHTML = '<span style="color:var(--dim);">(no trades yet)</span>';
    } else {
      rtDiv.innerHTML = rt.map(t => {
        const winCls = t.is_win ? 'badge-win' : 'badge-loss';
        const icon = t.is_win ? '✅' : '❌';
        const pnl = t.pnl_usd || 0;
        const pnlStr = (pnl >= 0 ? '+' : '') + pnl.toFixed(2);
        return `<div style="margin-bottom:2px;">${icon} <span class="badge ${t.side === 'UP' ? 'badge-up' : 'badge-down'}">${t.side}</span> $${(t.stake_usd || 0).toFixed(2)} → <span class="${pnl >= 0 ? 'green' : 'red'}">${pnlStr}</span> (${(t.pnl_pct || 0).toFixed(1)}%) <span style="color:var(--dim);">${t.time || ''}</span></div>`;
      }).join('');
    }

    const inPlay = ap.reduce((s, p) => s + (p.stake_usd || 0), 0);
    document.getElementById('summary-active').textContent = 'Active: ' + ap.length;
    document.getElementById('summary-inplay').textContent = 'In Play: $' + inPlay.toFixed(2);
    document.getElementById('summary-available').textContent = 'Available: $' + ((s.equity || 1000) - inPlay).toFixed(2);

    // --- Log ---
    const logs = s.log_entries || [];
    const logDiv = document.getElementById('log-stream');
    const recent = logs.slice(-18);
    if (recent.length === 0) {
      logDiv.innerHTML = '<div class="log-entry"><span class="log-time">--:--:--</span><span class="log-msg">等待交易信号...</span></div>';
    } else {
      logDiv.innerHTML = recent.map(e => {
        let cls = '';
        let prefix = '·';
        if (e.level === 'TRADE') { cls = 'trade'; prefix = '💰'; }
        else if (e.level === 'WARN') { cls = 'warn'; prefix = '⚠️'; }
        else if (e.level === 'ERROR') { cls = 'error'; prefix = '🚨'; }
        let msg = e.message || '';
        if (msg.length > 80) msg = msg.substring(0, 77) + '...';
        return `<div class="log-entry"><span class="log-time">${e.time || ''}</span><span class="log-msg ${cls}">${prefix} ${msg}</span></div>`;
      }).join('');
    }

    // --- Updated ---
    document.getElementById('last-updated').textContent = 'Last updated: ' + new Date().toLocaleTimeString();

  } catch (err) {
    console.error('Fetch error:', err);
  }
}

function renderDualChart(containerId, data1, data2) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const w = container.clientWidth || 500;
  const h = container.clientHeight || 150;
  const pad = { top: 10, right: 5, bottom: 20, left: 5 };
  const pw = w - pad.left - pad.right;
  const ph = h - pad.top - pad.bottom;

  let allVals = [];
  if (data1) allVals = allVals.concat(data1);
  if (data2) allVals = allVals.concat(data2);
  if (allVals.length < 2) {
    container.innerHTML = '<div style="color:var(--dim);text-align:center;padding-top:50px;">Waiting for data...</div>';
    return;
  }

  const min = Math.min(...allVals);
  const max = Math.max(...allVals);
  const range = max - min || 1;

  let svg = `<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">`;

  // 0.65 线
  const y65 = pad.top + ph - ((0.65 - min) / range) * ph;
  svg += `<line x1="${pad.left}" y1="${y65}" x2="${pad.left + pw}" y2="${y65}" stroke="#00d68f" stroke-width="0.5" stroke-dasharray="4,4"/>`;
  // 0.50 线
  const y50 = pad.top + ph - ((0.50 - min) / range) * ph;
  svg += `<line x1="${pad.left}" y1="${y50}" x2="${pad.left + pw}" y2="${y50}" stroke="#555" stroke-width="0.5" stroke-dasharray="4,4"/>`;

  if (data1) {
    const pts = data1.map((v, i) => {
      const x = pad.left + (i / (data1.length - 1)) * pw;
      const y = pad.top + ph - ((v - min) / range) * ph;
      return `${x},${y}`;
    });
    svg += `<polyline points="${pts.join(' ')}" fill="none" stroke="#00b4d8" stroke-width="1.5" stroke-linejoin="round"/>`;
  }

  if (data2) {
    const pts = data2.map((v, i) => {
      const x = pad.left + (i / (data2.length - 1)) * pw;
      const y = pad.top + ph - ((v - min) / range) * ph;
      return `${x},${y}`;
    });
    svg += `<polyline points="${pts.join(' ')}" fill="none" stroke="#c084fc" stroke-width="1.5" stroke-linejoin="round"/>`;
  }

  svg += `</svg>`;
  container.innerHTML = svg;
}

// 启动轮询
setInterval(fetchState, 1000);
fetchState();
</script>
</body>
</html>"""


# ============================================================
# Web 仪表盘类
# ============================================================

class WebDashboard:
    """浏览器仪表盘 — 使用内置 http.server，零额外依赖"""

    def __init__(self, port: int = 8186):
        self.port = port
        self._state = {
            "poly_latency_ms": 0.0,
            "binance_latency_ms": 0.0,
            "heartbeat": "STARTING",
            "equity": 1000.0,
            "initial_equity": 1000.0,
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "daily_pnl": 0.0,
            "btc_price": 0.0,
            "btc_change_pct": 0.0,
            "btc_history": [],
            "obi": 0.0,
            "obi_history": [],
            "gbm_win_prob": 0.0,
            "gbm_history": [],
            "poly_price_history": [],
            "ev": 0.0,
            "kelly_fraction": 0.0,
            "signal_side": "",
            "signal_stake": 0.0,
            "should_trade": False,
            "filter_reason": "",
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "time_to_expiry": 300.0,
            "active_positions": [],
            "recent_trades": [],
            "hourly_pnl": {},
            "log_entries": [],
        }
        self._lock = threading.Lock()
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def update(self, **kwargs):
        """更新仪表盘状态（线程安全）"""
        with self._lock:
            for key, value in kwargs.items():
                # 处理 deque/list 转 list
                if isinstance(value, deque):
                    value = list(value)
                if key == "hourly_pnl" and isinstance(value, dict):
                    value = dict(value)
                if key in ("active_positions", "recent_trades"):
                    value = list(value) if value else []
                if key == "log_entries":
                    value = [
                        {"time": e.get("time", e.get("time", "")),
                         "level": e.get("level", "INFO"),
                         "message": e.get("message", str(e))}
                        for e in (list(value) if isinstance(value, deque) else value)
                    ]
                self._state[key] = value

    def add_log(self, level: str, message: str):
        """添加日志条目"""
        with self._lock:
            timestamp = time.strftime("%H:%M:%S")
            self._state.setdefault("log_entries", []).append({
                "time": timestamp,
                "level": level,
                "message": message
            })
            # 保持最近 100 条
            if len(self._state["log_entries"]) > 100:
                self._state["log_entries"] = self._state["log_entries"][-100:]

    def _get_state_json(self) -> str:
        """获取当前状态 JSON"""
        with self._lock:
            return json.dumps(self._state, default=str)

    def start(self):
        """启动 Web 服务器（在后台线程中）"""
        state_ref = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # 抑制 HTTP 日志

            def do_GET(self):
                if self.path == "/" or self.path == "/index.html":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(WEB_HTML.encode("utf-8"))
                elif self.path == "/api/state":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(state_ref._get_state_json().encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

        # 尝试多个端口
        for port in range(self.port, self.port + 10):
            try:
                self._server = HTTPServer(("0.0.0.0", port), Handler)
                self.port = port
                break
            except OSError:
                continue

        if self._server is None:
            print("❌ Web dashboard: 无法绑定端口（8186-8089 均被占用）")
            return

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        url = f"http://localhost:{self.port}"
        print(f"🌐 Web Dashboard: {url}")

        # 自动打开浏览器
        def _open_browser():
            time.sleep(0.5)
            webbrowser.open(url)
        threading.Thread(target=_open_browser, daemon=True).start()

    def stop(self):
        """停止 Web 服务器"""
        if self._server:
            self._server.shutdown()
            self._server = None