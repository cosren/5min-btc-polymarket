#!/usr/bin/env python3
"""最终版: Polymarket BTC 5分钟数据获取

关键发现:
- outcomePrices 和 clobTokenIds 是 JSON 字符串，需要 json.loads()
- CLOB token ID 格式: 长数字字符串
- UP 价格: 0.515, DOWN 价格: 0.485
"""
import sys
import os
import json
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"


def get_current_slug() -> str:
    now = int(time.time())
    ts = now - (now % 300)
    return f"btc-updown-5m-{ts}"


def get_btc_market_full(slug: str):
    """获取 BTC 5分钟市场完整数据"""
    session = requests.Session()
    
    # 1. 获取市场数据
    resp = session.get(f"{GAMMA_URL}/markets", params={"slug": slug}, timeout=10)
    resp.raise_for_status()
    markets = resp.json()
    if not markets:
        return None
    market = markets[0]
    
    # 2. 获取市场详情
    market_id = market['id']
    resp = session.get(f"{GAMMA_URL}/markets/{market_id}", timeout=10)
    resp.raise_for_status()
    detail = resp.json()
    
    # 3. 解析 outcomePrices (JSON 字符串 -> Python 列表)
    outcome_prices_raw = detail.get('outcomePrices', '[]')
    if isinstance(outcome_prices_raw, str):
        outcome_prices = json.loads(outcome_prices_raw)
    else:
        outcome_prices = outcome_prices_raw
    
    # 4. 解析 clobTokenIds (JSON 字符串 -> Python 列表)
    clob_token_ids_raw = detail.get('clobTokenIds', '[]')
    if isinstance(clob_token_ids_raw, str):
        clob_token_ids = json.loads(clob_token_ids_raw)
    else:
        clob_token_ids = clob_token_ids_raw
    
    # 5. 获取事件数据
    resp = session.get(f"{GAMMA_URL}/events", params={"slug": slug}, timeout=10)
    resp.raise_for_status()
    events = resp.json()
    event = events[0] if events else {}
    
    up_price = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.5
    down_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.5
    
    return {
        'slug': slug,
        'market_id': market_id,
        'event_id': event.get('id'),
        'question': market.get('question'),
        'title': event.get('title'),
        'up_price': up_price,
        'down_price': down_price,
        'volume': float(event.get('volume', 0)),
        'liquidity': float(market.get('liquidity', 0)),
        'end_date': market.get('endDate'),
        'start_date': event.get('startDate'),
        'clob_token_ids': clob_token_ids,
        'condition_id': market.get('conditionId'),
        'side': 'UP' if up_price > down_price else 'DOWN',
    }


def get_clob_prices(token_id: str):
    """获取 CLOB 价格数据"""
    session = requests.Session()
    results = {}
    
    # 尝试获取价格
    try:
        resp = session.get(f"{CLOB_URL}/price", params={"token_id": token_id}, timeout=10)
        if resp.status_code == 200:
            results['price'] = resp.json()
    except Exception as e:
        results['price_error'] = str(e)
    
    # 尝试获取订单簿
    try:
        resp = session.get(f"{CLOB_URL}/book", params={"token_id": token_id}, timeout=10)
        if resp.status_code == 200:
            book = resp.json()
            results['best_bid'] = book.get('bids', [{}])[0] if book.get('bids') else None
            results['best_ask'] = book.get('asks', [{}])[0] if book.get('asks') else None
    except Exception as e:
        results['book_error'] = str(e)
    
    return results


def get_historical_btc_prices(limit: int = 5):
    """获取历史 BTC 价格数据（用于回测）"""
    now = int(time.time())
    results = []
    
    for i in range(limit):
        ts = now - (i * 300) - (now % 300)
        slug = f"btc-updown-5m-{ts}"
        
        try:
            data = get_btc_market_full(slug)
            if data:
                results.append(data)
        except Exception:
            pass
    
    return results


def main():
    print("=" * 60)
    print("  BTC 5分钟市场 - 最终数据获取")
    print("=" * 60)
    
    # 当前市场
    slug = get_current_slug()
    print(f"\n当前 slug: {slug}")
    
    data = get_btc_market_full(slug)
    if data:
        print("\n" + "-" * 40)
        print("完整市场数据:")
        print("-" * 40)
        print(f"  Event ID:      {data['event_id']}")
        print(f"  Market ID:     {data['market_id']}")
        print(f"  Title:         {data['title']}")
        print(f"  UP 价格:       {data['up_price']:.3f}")
        print(f"  DOWN 价格:     {data['down_price']:.3f}")
        print(f"  价差:          {data['up_price'] + data['down_price']:.3f}")
        print(f"  成交量:        ${data['volume']:,.2f}")
        print(f"  流动性:        ${data['liquidity']:,.2f}")
        print(f"  到期时间:      {data['end_date']}")
        print(f"  Condition ID:  {data['condition_id']}")
        print(f"  Token IDs:     {data['clob_token_ids']}")
        
        # CLOB 价格
        if data['clob_token_ids']:
            print("\n" + "-" * 40)
            print("CLOB 价格数据:")
            print("-" * 40)
            for i, token_id in enumerate(data['clob_token_ids']):
                side = "UP" if i == 0 else "DOWN"
                print(f"\n  [{side}] Token: {token_id[:20]}...")
                prices = get_clob_prices(token_id)
                if 'price' in prices:
                    print(f"    价格: {prices['price']}")
                if 'best_bid' in prices:
                    print(f"    最佳买价: {prices['best_bid']}")
                if 'best_ask' in prices:
                    print(f"    最佳卖价: {prices['best_ask']}")
                if 'price_error' in prices:
                    print(f"    ❌ 价格: {prices['price_error']}")
                if 'book_error' in prices:
                    print(f"    ❌ 订单簿: {prices['book_error']}")
    
    # 历史数据
    print("\n" + "-" * 40)
    print("历史 BTC 价格:")
    print("-" * 40)
    historical = get_historical_btc_prices(5)
    for h in historical:
        print(f"  {h['slug'][-10:]}: UP={h['up_price']:.3f} DOWN={h['down_price']:.3f} | {h['title'][:40]}")
    
    print("\n" + "=" * 60)
    print("  ✅ 数据获取成功！")
    print("=" * 60)
    print("""
API 调用总结:
  1. Gamma API /markets?slug={slug}          → 市场基本信息
  2. Gamma API /markets/{market_id}          → 市场详情 + 价格
  3. Gamma API /events?slug={slug}           → 事件信息
  
价格数据:
  - outcomePrices: JSON 字符串，需 json.loads()
  - clobTokenIds:  JSON 字符串，需 json.loads()
  - UP 价格: outcomePrices[0]
  - DOWN 价格: outcomePrices[1]
""")


if __name__ == '__main__':
    main()