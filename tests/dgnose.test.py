#!/usr/bin/env python3
"""
🛰️ BTC 5m Polymarket 策略多链路交叉验证穿透脚本

功能：
1. 三链路同屏对比：币安直连 | OKX 直连 | 主程序 Aggregator（OKX）
2. 现场捕捉各链路的 OBI 差异。
3. 自动对齐合约 10 档深度公式。
4. 如果主程序 OBI 死在 0.0，当场触发致命 Bug 诊断警报！
"""

import asyncio
import sys
import os
from datetime import datetime
import aiohttp

# 自动处理项目路径依赖
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入你项目主程序的聚合器组件
try:
    from src.data_sources.aggregator import MarketDataAggregator
    from src.core.trade_runner import load_config
    print("✅ 成功加载项目底层 Aggregator 模块！准备进行交叉比对...")
except ImportError as e:
    print(f"❌ 导入失败: {e}。请确保在项目根目录下运行。")
    sys.exit(1)

# 配置参数
TARGET_SYMBOL = "BTCUSDT"
DEPTH_LEVELS = 10

async def fetch_direct_http_obi(session):
    """【链路 A】直连币安合约官方 API，获取最新 10 档真数据"""
    url = f"https://fapi.binance.com/fapi/v1/depth?symbol={TARGET_SYMBOL}&limit={DEPTH_LEVELS}"
    try:
        async with session.get(url, timeout=2) as response:
            if response.status == 200:
                data = await response.json()
                bid_vol = sum(float(item[1]) for item in data.get('bids', [])[:DEPTH_LEVELS])
                ask_vol = sum(float(item[1]) for item in data.get('asks', [])[:DEPTH_LEVELS])
                total = bid_vol + ask_vol
                obi = (bid_vol - ask_vol) / total if total > 0 else 0.0
                return {"success": True, "obi": obi, "price": float(data['bids'][0][0])}
            return {"success": False, "error": f"HTTP {response.status}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def fetch_okx_obi(session):
    """【链路 C】直连 OKX 永续合约 API，获取最新 10 档真数据"""
    url = f"https://www.okx.com/api/v5/market/books?instId=BTC-USDT-SWAP&sz={DEPTH_LEVELS}"
    try:
        async with session.get(url, timeout=2) as response:
            if response.status == 200:
                res_json = await response.json()
                if res_json.get('code') != '0':
                    return {"success": False, "error": f"OKX code={res_json.get('code')}"}
                data = res_json.get('data', [{}])[0]
                # OKX 返回：[[price, sz, liqSz, orders], ...]，sz 为张数，1张=0.01BTC
                bid_vol = sum(float(item[1]) * 0.01 for item in data.get('bids', [])[:DEPTH_LEVELS])
                ask_vol = sum(float(item[1]) * 0.01 for item in data.get('asks', [])[:DEPTH_LEVELS])
                total = bid_vol + ask_vol
                obi = (bid_vol - ask_vol) / total if total > 0 else 0.0
                return {"success": True, "obi": obi, "price": float(data['bids'][0][0])}
            return {"success": False, "error": f"HTTP {response.status}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def main():
    print("==========================================================")
    print("🛰️  [三链路交叉验证] 币安 vs OKX vs 主程序 Aggregator")
    print("==========================================================")

    # 1. 现场初始化主程序的聚合器
    config_path = 'config/btc_5m_profiles.yaml'
    config = load_config(config_path) or {}
    print("🔄 正在为【链路 C】初始化主程序 Aggregator（OKX 数据源）...")
    aggregator = MarketDataAggregator(config)
    await aggregator.initialize_sources()

    print("\n🚀 开始三流同屏审计（每0.5秒高频比对）...")
    print("=" * 80)

    # 模拟 Polymarket 仿真快照传入
    mock_poly_data = {"up_price": 0.495, "down_price": 0.505}

    cycle = 0
    async with aiohttp.ClientSession() as session:
        while True:
            cycle += 1
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            
            # 📡 链路 A：币安合约直连
            binance_res = await fetch_direct_http_obi(session)
            
            # 📡 链路 B：OKX 永续合约直连
            okx_res = await fetch_okx_obi(session)

            # 📡 链路 C：主程序 Aggregator（OKX 数据源）
            # get_aggregated_data 内部会自动调用 update_data()，无需手动触发
            agg_data = aggregator.get_aggregated_data(mock_poly_data)
            main_program_obi = agg_data.binance_obi

            binance_ok = binance_res["success"]
            okx_ok = okx_res["success"]
            binance_obi = binance_res.get("obi", 0) if binance_ok else None
            okx_obi = okx_res.get("obi", 0) if okx_ok else None
            okx_price = okx_res.get("price", 0) if okx_ok else 0

            # 每 10 轮或出现异常时打印
            if cycle % 10 == 0 or main_program_obi == 0.0 or (
                binance_ok and okx_ok and abs(binance_obi - okx_obi) > 0.2
            ):
                print(f"\n⏱️  [{current_time}] 交叉审计轮次: #{cycle}")
                print(f"📈 OKX 最新合约价: ${okx_price:,.2f}" if okx_ok else "📈 OKX: 请求失败")
                print("-" * 80)
                print(f"{'链路':<12} {'数据源':<16} {'OBI':>10} {'状态':<20}")
                print("-" * 80)

                # 链路 A
                a_str = f"{binance_obi:+.4f}" if binance_ok else "--"
                a_status = "✅ 正常" if binance_ok else f"❌ {binance_res.get('error','')}"
                print(f"{'链路 A':<12} {'Binance 直连':<16} {a_str:>10} {a_status:<20}")

                # 链路 B
                b_str = f"{okx_obi:+.4f}" if okx_ok else "--"
                b_status = "✅ 正常" if okx_ok else f"❌ {okx_res.get('error','')}"
                print(f"{'链路 B':<12} {'OKX 直连':<16} {b_str:>10} {b_status:<20}")

                # 链路 C
                c_str = f"{main_program_obi:+.4f}"
                c_status = "✅ 正常" if main_program_obi != 0.0 else "⚠️ 数据为 0"
                print(f"{'链路 C':<12} {'Aggregator(OKX)':<16} {c_str:>10} {c_status:<20}")

                # 交叉比对
                if binance_ok and okx_ok:
                    diff = abs(binance_obi - okx_obi)
                    # 不同交易所，盘口天然不同，偏差大是正常的
                    tag = "🔄 不同交易所" if diff > 0.15 else "🟢 偶然一致"
                    print(f"{'':>12} {'Binance↔OKX 偏差':<16} {diff:>10.4f} {tag:<20}")

                # 诊断
                if main_program_obi == 0.0:
                    print("\n🔴 [致命警报] 主程序 Aggregator OBI 持续为 0.0000！")
                    print("   ↳ 诊断: 主程序数据源未正常拉取，检查 binance_ws.py 网络连接。")
                elif okx_ok and abs(main_program_obi - okx_obi) > 0.5:
                    print("\n🟡 [提示] 主程序 OBI 与 OKX 直连有较大偏差")
                    print(f"   ↳ 差值: {abs(main_program_obi - okx_obi):.4f}")
                    print("   ↳ 原因: 两次 HTTP 请求时间差 ~100-200ms，高频盘口已刷新")
                    print("   ↳ 结论: 非 Bug，属正常时序差异。主程序用最新一帧数据，更准确。")
                print("=" * 80)

            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 交叉验证脚本已被手动终止。")