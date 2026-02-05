"""
Futures Intelligence Signal Bot - Telegram Interface
Sends rich-formatted alerts with inline buttons.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from scanner import ScanResult
from inspector import OnChainSignal, SignalType

logger = logging.getLogger(__name__)


@dataclass
class AlertMessage:
    """Structured alert data for Telegram."""
    symbol: str
    base_asset: str
    price: float
    price_change: float
    volume_spike: float
    signal: OnChainSignal
    token_address: Optional[str] = None
    chain: str = "ethereum"


class TelegramReporter:
    """
    Sends rich-formatted trading signals to Telegram.
    
    Features:
    - Markdown formatting
    - Inline keyboard buttons (Chart, Etherscan)
    - Error handling with retries
    """

    def __init__(
        self,
        bot_token: str = TELEGRAM_BOT_TOKEN,
        chat_id: str = TELEGRAM_CHAT_ID
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._bot: Optional[Bot] = None
        self._application: Optional[Application] = None

    @property
    def bot(self) -> Bot:
        """Lazy initialization of Telegram bot."""
        if self._bot is None:
            self._bot = Bot(token=self.bot_token)
        return self._bot

    def format_signal_message(
        self,
        scan_result: ScanResult,
        signal: OnChainSignal
    ) -> str:
        """
        Format a rich alert message.
        
        Returns:
            Formatted markdown string
        """
        price_emoji = "📈" if scan_result.price_change_1h > 0 else "📉"
        
        message_lines = [
            f"🚨 *SIGNAL DETECTED: #{scan_result.base_asset}*",
            "",
            "📊 *Market Data:*",
            f"• Price: `${scan_result.current_price:,.4f}` ({scan_result.price_change_1h:+.2f}% {price_emoji})",
            f"• Vol Spike: `{scan_result.volume_spike_ratio:.0f}x` average",
            f"• Trigger: {scan_result.trigger_reason}",
            "",
            "🔗 *On-Chain Intel:*",
            f"• Bias: {signal.bias_emoji} *{signal.bias_text}*",
            f"• Confidence: `{signal.confidence_score}%`",
        ]

        if signal.evidence:
            message_lines.append("• Reason:")
            for evidence in signal.evidence[:3]:
                clean_evidence = evidence.replace("_", "\\_").replace("*", "\\*")
                message_lines.append(f"  └ {clean_evidence}")

        if signal.whale_transfers > 0:
            message_lines.append(f"• Whale Activity: {signal.whale_transfers} transfers")

        if signal.exchange_deposits > 0:
            message_lines.append(f"• Exchange Deposits: `${signal.exchange_deposits:,.0f}`")
        if signal.exchange_withdrawals > 0:
            message_lines.append(f"• Exchange Withdrawals: `${signal.exchange_withdrawals:,.0f}`")

        message_lines.extend([
            "",
            f"⏰ _Analyzed {signal.analyzed_transfers} on-chain transfers_"
        ])

        return "\n".join(message_lines)

    def create_inline_keyboard(
        self,
        symbol: str,
        token_address: Optional[str] = None,
        chain: str = "ethereum"
    ) -> InlineKeyboardMarkup:
        """
        Create inline keyboard with Chart and Explorer buttons.
        
        Returns:
            InlineKeyboardMarkup with action buttons
        """
        base_asset = symbol.split('/')[0].replace(':USDT', '')
        
        buttons = []

        tradingview_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{base_asset}USDT.P"
        buttons.append(
            InlineKeyboardButton("📊 TradingView", url=tradingview_url)
        )

        binance_url = f"https://www.binance.com/en/futures/{base_asset}USDT"
        buttons.append(
            InlineKeyboardButton("💹 Binance", url=binance_url)
        )

        if token_address:
            if chain == "bsc":
                explorer_url = f"https://bscscan.com/token/{token_address}"
                buttons.append(
                    InlineKeyboardButton("🔍 BSCScan", url=explorer_url)
                )
            else:
                explorer_url = f"https://etherscan.io/token/{token_address}"
                buttons.append(
                    InlineKeyboardButton("🔍 Etherscan", url=explorer_url)
                )

        keyboard = [buttons[:2]]
        if len(buttons) > 2:
            keyboard.append([buttons[2]])

        return InlineKeyboardMarkup(keyboard)

    async def send_alert(
        self,
        scan_result: ScanResult,
        signal: OnChainSignal,
        chat_id: Optional[str] = None
    ) -> bool:
        """
        Send a formatted alert to Telegram.
        
        Args:
            scan_result: Market scan result
            signal: On-chain analysis signal
            chat_id: Override default chat ID
            
        Returns:
            True if sent successfully
        """
        target_chat = chat_id or self.chat_id
        
        if target_chat == "YOUR_CHAT_ID_HERE":
            logger.warning("Telegram chat ID not configured")
            return False

        message = self.format_signal_message(scan_result, signal)
        keyboard = self.create_inline_keyboard(
            scan_result.symbol,
            scan_result.token_address,
            scan_result.chain
        )

        try:
            await self.bot.send_message(
                chat_id=target_chat,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            logger.info(f"Alert sent for {scan_result.symbol}")
            return True

        except TelegramError as e:
            logger.error(f"Telegram error: {e}")
            try:
                plain_message = message.replace("*", "").replace("`", "").replace("_", "")
                await self.bot.send_message(
                    chat_id=target_chat,
                    text=plain_message,
                    reply_markup=keyboard
                )
                return True
            except Exception as e2:
                logger.error(f"Fallback also failed: {e2}")
                return False

        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            return False

    async def send_simple_message(
        self,
        text: str,
        coin_name: Optional[str] = None,
        chat_id: Optional[str] = None
    ) -> bool:
        """Send a simple text message."""
        target_chat = chat_id or self.chat_id
        
        try:
            await self.bot.send_message(
                chat_id=target_chat,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    
    async def send_startup_message(self) -> bool:
        """Send bot startup notification."""
        message = (
            "🤖 *Futures Intelligence Bot Started*\n\n"
            "✅ Scanner: Active\n"
            "✅ On-Chain Inspector: Active\n"
            "✅ Telegram Reporter: Active\n\n"
            "_Monitoring Binance Futures for signals..._"
        )
        return await self.send_simple_message(message)
    
    async def initialize_callback_handler(self):
        """Initialize Telegram bot application with callback handler."""
        if self._application is not None:
            logger.info("Callback handler already initialized")
            return
        
        try:
            self._application = Application.builder().token(self.bot_token).build()
            
            # Add callback query handler (currently unused, ready for future features)
            async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
                """Handle button clicks."""
                query = update.callback_query
                await query.answer("Button clicked!")
            
            self._application.add_handler(CallbackQueryHandler(button_callback))
            
            # Start the application
            await self._application.initialize()
            await self._application.start()
            
            # Start polling in background
            asyncio.create_task(self._application.updater.start_polling(drop_pending_updates=True))
            
            logger.info("✅ Telegram callback handler initialized")
        except Exception as e:
            logger.error(f"Failed to initialize callback handler: {e}")
    
    async def shutdown(self):
        """Shutdown the Telegram application."""
        if self._application:
            try:
                await self._application.stop()
                await self._application.shutdown()
                logger.info("Telegram application shutdown complete")
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")


async def test_alert():
    """Test sending an alert."""
    logging.basicConfig(level=logging.INFO)
    
    from scanner import ScanResult
    from inspector import OnChainSignal, SignalType
    from datetime import datetime

    scan_result = ScanResult(
        symbol="ETH/USDT:USDT",
        base_asset="ETH",
        current_price=2847.52,
        price_change_1h=4.2,
        volume_5m=1500000,
        avg_volume_1h=500000,
        volume_spike_ratio=3.0,
        trigger_reason="Volume Spike: 3.0x | Price 📈: +4.20%",
        token_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        chain="ethereum"
    )

    signal = OnChainSignal(
        signal_type=SignalType.SHORT,
        confidence_score=85,
        evidence=[
            "🔴 Whale 1 → Binance Hot Wallet: $2,500,000",
            "🔴 Whale 2 → Coinbase: $1,800,000"
        ],
        whale_transfers=2,
        exchange_deposits=4300000,
        exchange_withdrawals=0,
        analyzed_transfers=50
    )

    reporter = TelegramReporter()
    success = await reporter.send_alert(scan_result, signal)
    
    if success:
        print("✅ Test alert sent successfully!")
    else:
        print("❌ Failed to send test alert. Check your config.py")


if __name__ == "__main__":
    asyncio.run(test_alert())
