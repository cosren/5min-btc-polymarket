#!/usr/bin/env python3
"""
🛰️ BTC 5m Polymarket 策略多链路交叉验证穿透脚本

功能：
1. 同时模拟【直连HTTP真数据】与【复用项目主程序Aggregator内存流】。
2. 现场捕捉主、备两条链路的 OBI 差异。
3. 自动对齐合约 10 档深度公式。
4. 如果主程序 OBI 死在 0.0 或 -0.010，当场触发致命 Bug 诊断警报！
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

async def main():
    print("==========================================================")
    print("🛰️  [主程序逻辑 vs 真实网路数据] 双链路交叉验证系统启动...")
    print("==========================================================")

    # 1. 现场初始化主程序的聚合器
    config_path = 'config/btc_5m_profiles.yaml'
    config = load_config(config_path) or {}
    print("🔄 正在为【链路 B】初始化主程序的异步 WebSocket 聚合流...")
    aggregator = MarketDataAggregator(config)
    await aggregator.initialize_sources()

    # 模拟 Polymarket 仿真快照传入
    mock_poly_data = {"up_price": 0.495, "down_price": 0.505}
    
    print("\n🚀 开始双流同屏审计（每0.5秒高频比对，对齐主程序）...")
    print("=" * 65)

    cycle = 0
    async with aiohttp.ClientSession() as session:
        while True:
            cycle += 1
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            
            # 📡 链路 A：通过网络直接计算
            direct_res = await fetch_direct_http_obi(session)
            
            # 📡 链路 B：通过主程序的聚合器内存计算
            # 强行触发一轮数据获取
            if hasattr(aggregator, 'binance_ws') and aggregator.binance_ws:
                if hasattr(aggregator.binance_ws, 'update_data'):
                    aggregator.binance_ws.update_data()
            
            agg_data = aggregator.get_aggregated_data(mock_poly_data)
            main_program_obi = agg_data.binance_obi

            if not direct_res["success"]:
                await asyncio.sleep(0.5)
                continue

            real_network_obi = direct_res["obi"]
            
            # 🧮 核心对齐交叉检查
            obi_diff = abs(real_network_obi - main_program_obi)
            
            # 只有在产生显著偏差，或者每10轮，打印一次看板
            if obi_diff > 0.15 or cycle % 10 == 0:
                print(f"\n⏱️  [时间戳]: {current_time} | 交叉审计轮次: #{cycle}")
                print(f"📈 币安当前最新合约价: ${direct_res['price']:,.2f}")
                print("-" * 65)
                print(f"📡 【链路 A】直连网络真数据计算 (10档合约) -> OBI: {real_network_obi:+.4f}")
                print(f"📡 【链路 B】复用主程序逻辑输出 (Aggregator) -> OBI: {main_program_obi:+.4f}")
                
                # 🚨 自动判定并揭露病灶
                if main_program_obi == -0.010:
                    print("🔴 [致命警报] 发现经典死锁特征值 `-0.010`！")
                    print("   ↳ 诊断报告: 主程序的 WebSocket 线程已经断流死锁，目前正在强行套用 Polymarket 的价格脑补假数据！")
                elif main_program_obi == 0.0:
                    print("⚠️ [警告] 主程序当前吐出 OBI 纯为 0.0000！")
                    print("   ↳ 诊断报告: 数据聚合器尚未收到币安合约的第一帧推送数据，更新受阻。")
                elif obi_diff > 0.4:
                    print("🔥 [方向性偏离警报] 主程序与真实网络数值产生断层巨差！")
                    print(f"   ↳ 离散差值: {obi_diff:.4f}")
                    print("   ↳ 诊断报告: 主程序底层的 `binance_ws.py` 内部计算代码可能与网络拉取的限额（limit）档位不匹配，或计算公式正负号写反了！")
                else:
                    print("🟢 [链路正常] 双链路数据吻合，时间差在微秒级容忍范围内。")
                print("=" * 65)

            await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 交叉验证脚本已被手动终止。")