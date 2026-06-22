#!/usr/bin/env python3
"""Telegram/微信通知模块

用于发送交易警报、风控警报和每小时总结
"""
import time
import logging
from typing import Optional, Dict, Any

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram通知器
    
    功能:
    - 发送交易警报
    - 发送风控警报
    - 发送每小时总结
    
    使用示例:
        notifier = TelegramNotifier(
            bot_token='YOUR_BOT_TOKEN',
            chat_id='YOUR_CHAT_ID'
        )
        notifier.send_trade_alert({
            'side': 'UP',
            'market': 'btc-updown-5m-123456',
            'stake': 5.0,
            'price': 0.75
        })
    """
    
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        api_url: str = 'https://api.telegram.org/bot'
    ):
        """初始化
        
        Args:
            bot_token: Telegram Bot Token
            chat_id: 聊天ID
            api_url: Telegram API URL
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = api_url
        self._message_count = 0
    
    def _send_message(self, text: str, parse_mode: str = 'HTML') -> bool:
        """发送消息
        
        Args:
            text: 消息文本
            parse_mode: 解析模式
        
        Returns:
            True表示发送成功
        """
        if requests is None:
            logger.error("requests not installed, cannot send message")
            return False
        
        url = f"{self.api_url}{self.bot_token}/sendMessage"
        
        payload = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                self._message_count += 1
                return True
            else:
                logger.error(f"Failed to send message: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    def send_trade_alert(self, trade_data: Dict[str, Any]) -> bool:
        """发送交易警报
        
        Args:
            trade_data: 交易数据
        
        Returns:
            True表示发送成功
        """
        text = (
            "🔔 <b>交易警报</b>\n\n"
            f"方向: <b>{trade_data.get('side', 'N/A')}</b>\n"
            f"市场: {trade_data.get('market', 'N/A')}\n"
            f"下注: ${trade_data.get('stake', 0):.2f}\n"
            f"价格: {trade_data.get('price', 0):.4f}\n"
            f"时间: {trade_data.get('timestamp', time.strftime('%Y-%m-%d %H:%M:%S'))}\n"
        )
        
        if trade_data.get('pnl') is not None:
            pnl = trade_data['pnl']
            emoji = "✅" if pnl >= 0 else "❌"
            text += f"\n{emoji} 盈亏: ${pnl:.2f}\n"
        
        return self._send_message(text)
    
    def send_risk_alert(self, risk_event: str, details: Optional[Dict] = None) -> bool:
        """发送风控警报
        
        Args:
            risk_event: 风控事件描述
            details: 详细信息
        
        Returns:
            True表示发送成功
        """
        text = (
            "🚨 <b>风控警报</b>\n\n"
            f"事件: <b>{risk_event}</b>\n"
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        
        if details:
            text += "\n详细信息:\n"
            for key, value in details.items():
                text += f"- {key}: {value}\n"
        
        return self._send_message(text)
    
    def send_hourly_summary(self, summary: Dict[str, Any]) -> bool:
        """发送每小时总结
        
        Args:
            summary: 总结数据
        
        Returns:
            True表示发送成功
        """
        text = (
            "📊 <b>每小时总结</b>\n\n"
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"交易次数: {summary.get('trades', 0)}\n"
            f"胜率: {summary.get('win_rate', 0):.1f}%\n"
            f"总盈亏: ${summary.get('total_pnl', 0):.2f}\n"
            f"平均盈亏: ${summary.get('avg_pnl', 0):.2f}\n"
        )
        
        if summary.get('max_drawdown') is not None:
            text += f"最大回撤: {summary.get('max_drawdown', 0):.2f}%\n"
        
        if summary.get('circuit_breaker_active'):
            text += "\n⚠️ <b>熔断器已激活</b>\n"
        
        return self._send_message(text)
    
    def send_system_alert(self, message: str) -> bool:
        """发送系统警报
        
        Args:
            message: 消息内容
        
        Returns:
            True表示发送成功
        """
        text = (
            "⚙️ <b>系统警报</b>\n\n"
            f"{message}\n\n"
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        
        return self._send_message(text)
    
    @property
    def message_count(self) -> int:
        """获取已发送消息数量"""
        return self._message_count