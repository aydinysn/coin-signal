"""
Futures Intelligence Signal Bot - Main Orchestrator
Async loop that runs Scanner -> Inspector -> Telegram Alert.
"""

import asyncio
import logging
import signal as os_signal
import sys
from datetime import datetime
from typing import Optional
import ccxt.async_support as ccxt
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from config import (
    SCAN_INTERVAL_SECONDS,
    LOG_LEVEL,
    LOG_FORMAT,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID
)
from scanner import BinanceFuturesScanner, ScanResult
from inspector import OnChainInspector, OnChainSignal, SignalType
from bot_interface import TelegramReporter
from analyzer import get_advanced_analysis
from signal_manager import SignalManager

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Suppress httpx and telegram INFO logs (they pollute console with every API call)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)




class FuturesIntelligenceBot:
    """
    Main orchestrator for the Futures Intelligence Signal Bot.
    
    Pipeline: Scanner -> Inspector -> Telegram Alert
    Runs every 30 seconds (configurable).
    """

    def __init__(self):
        self.scanner: Optional[BinanceFuturesScanner] = None
        self.inspector: Optional[OnChainInspector] = None
        self.reporter: Optional[TelegramReporter] = None
        self.exchange: Optional[ccxt.binance] = None
        self.signal_manager: Optional[SignalManager] = None
        self._running: bool = False
        self._alerted_symbols: set = set()
        self._alert_cooldown: dict = {}

    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing Futures Intelligence Bot...")
        
        self.scanner = BinanceFuturesScanner()
        self.inspector = OnChainInspector()
        self.reporter = TelegramReporter()
        
        # Initialize signal manager for dashboard
        self.signal_manager = SignalManager()
        
        # Initialize CCXT for momentum analysis
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        # Initialize Telegram callback handler
        await self.reporter.initialize_callback_handler()

        if TELEGRAM_BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
            await self.reporter.send_startup_message()
        else:
            logger.warning("Telegram not configured - alerts will be logged only")

        logger.info("✅ All components initialized")

    async def shutdown(self):
        """Gracefully shutdown all components."""
        logger.info("Shutting down...")
        self._running = False
        
        if self.scanner:
            await self.scanner.close()
        if self.inspector:
            await self.inspector.close()
        if self.exchange:
            await self.exchange.close()
        if self.reporter:
            await self.reporter.shutdown()
        
        logger.info("Shutdown complete")

    def _should_alert(self, symbol: str) -> bool:
        """
        Check if we should alert for this symbol (cooldown logic).
        Prevents spam by enforcing 5-minute cooldown per symbol.
        """
        now = datetime.now()
        last_alert = self._alert_cooldown.get(symbol)
        
        if last_alert is None:
            return True
        
        cooldown_seconds = 300
        if (now - last_alert).total_seconds() > cooldown_seconds:
            return True
        
        return False

    def _mark_alerted(self, symbol: str):
        """Mark symbol as recently alerted."""
        self._alert_cooldown[symbol] = datetime.now()

    async def process_opportunity(
        self,
        scan_result: ScanResult
    ) -> Optional[OnChainSignal]:
        """
        Process a single scan result through the full pipeline.
        Uses dynamic token address resolution via DEX Screener.
        
        Args:
            scan_result: Detected market opportunity
            
        Returns:
            OnChainSignal if analysis was successful
        """
        # Use dynamic address resolution - checks config first, then DEX Screener
        signal = await self.inspector.inspect_by_symbol(
            symbol=scan_result.base_asset,
            chain=scan_result.chain if scan_result.chain != "unknown" else "ethereum",
            current_price=scan_result.current_price
        )

        return signal

    async def run_scan_cycle(self):
        """Execute one complete scan cycle - HYBRID MODE."""
        cycle_start = datetime.now()
        logger.info(f"{'='*50}")
        logger.info(f"Starting scan cycle at {cycle_start.strftime('%H:%M:%S')}")

        try:
            opportunities = await self.scanner.scan(max_concurrent=15)

            if not opportunities:
                logger.info("No significant opportunities found this cycle.")
                return

            logger.info(f"Found {len(opportunities)} potential opportunities")

            # BULUNAN HER FIRSAT İÇİN (ilk 5 tanesini işle)
            for scan_result in opportunities[:5]:
                if not self._should_alert(scan_result.symbol):
                    logger.debug(f"Skipping {scan_result.symbol} - cooldown active")
                    continue

                # 1. GELİŞMİŞ ANALİZ (YENİ ANALİST MODU!)
                analysis = await get_advanced_analysis(self.exchange, scan_result.symbol)
                
                # Eğer analiz başarısızsa bu coini atla
                if not analysis:
                    logger.warning(f"⚠️ {scan_result.symbol} - Analiz verisi alınamadı, atlanıyor")
                    continue
                
                # ============================================================
                # 🛑 FİLTRE: 5 Dakikalık Değişim %1'den Azsa ATLA
                # ============================================================
                pct_val = analysis['change_5m']
                
                if abs(pct_val) < 1.0:
                    logger.info(f"💤 {scan_result.symbol} pas geçildi: 5dk değişim %{pct_val:.2f} (Limit: >%1.0)")
                    continue  # Bu coini geç, mesaj atma!
                # ============================================================

                # 2. On-Chain Analiz Yapmaya Çalış
                try:
                    signal = await self.process_opportunity(scan_result)
                except Exception as e:
                    logger.error(f"Inspector error for {scan_result.symbol}: {e}")
                    signal = None

                # 3. BAŞLIK İKONU BELİRLE (Hibrit Mantık)
                if signal and signal.signal_type in [SignalType.SHORT, SignalType.LONG]:
                    header_icon = "🚨 BALİNA TESPİT EDİLDİ"
                    severity = "HIGH"
                else:
                    header_icon = "⚠️ TEKNİK TARAMA (SCALP)"
                    severity = "LOW"

                # 4. ULTRA-SIMPLE MESAJ FORMATI (YENİ!)
                # Format: COIN - EMOJI - BB_PRICE - 5M_%
                
                # 1. Coin Adı (Sadece sembol)
                coin_name = analysis['symbol'].split('/')[0]
                
                # 2. Yön Emojisi ve Bollinger Band Fiyatı
                if analysis['direction'] == "LONG":
                    emoji = "🟢"
                    # Yükseliyorsa Alt Band'ı göster (destek seviyesi)
                    bb_target = analysis['bb_lower']
                else:
                    emoji = "🔴"
                    # Düşüyorsa Üst Band'ı göster (direnç seviyesi)
                    bb_target = analysis['bb_upper']
                
                # 3. 5 Dakikalık Yüzde Formatla
                if pct_val > 0:
                    pct_str = f"+%{pct_val:.2f}"
                else:
                    pct_str = f"%{pct_val:.2f}"
                
                # 4. Hacim değerini formatlı göster (300K, 1.5M gibi)
                volume_usd = scan_result.volume_usd_5m
                if volume_usd >= 1_000_000:
                    volume_str = f"{volume_usd / 1_000_000:.1f}M"
                elif volume_usd >= 1_000:
                    volume_str = f"{volume_usd / 1_000:.0f}K"
                else:
                    volume_str = f"{volume_usd:.0f}"
                
                # FINAL COMPACT MESSAGE - YENİ SIRALAMA
                # Format: #COIN 🟢 Fiyat: $95,234.56 | 300K | 3.2x | BB: 45234.5678 | +%0.85
                volume_spike = scan_result.volume_spike_ratio
                current_price = scan_result.current_price
                
                # Fiyat formatlaması - küçük fiyatlar için daha fazla basamak
                if current_price >= 1:
                    price_str = f"${current_price:,.2f}"
                elif current_price >= 0.01:
                    price_str = f"${current_price:.4f}"
                else:
                    # Çok küçük fiyatlar için (örn: $0.000023)
                    price_str = f"${current_price:.8f}".rstrip('0').rstrip('.')
                
                message = f"#{coin_name} {emoji} Fiyat: {price_str} | {volume_str} | {volume_spike:.1f}x | BB: {bb_target:.4f} | {pct_str}\n\n"
                
                # Linkler (sadeleştirilmiş)
                tv_link = f"https://www.tradingview.com/chart/?symbol=BINANCE%3A{coin_name}USDT.P"
                binance_link = f"https://www.binance.com/en/futures/{coin_name}USDT"
                message += f"[TradingView]({tv_link}) | [Binance]({binance_link})"

                # 5. LOG VE TELEGRAM'A GÖNDER
                logger.info(
                    f"{'🚨' if severity == 'HIGH' else '⚠️'} SIGNAL: {coin_name} | "
                    f"{emoji} | BB: {bb_target:.4f} | 5m: {pct_str}"
                )

                if self.reporter and TELEGRAM_BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
                    await self.reporter.send_simple_message(message, coin_name=coin_name)
                
                # Send signal to dashboard
                self.signal_manager.add_signal({
                    'coin': coin_name,
                    'emoji': emoji,
                    'price': current_price,
                    'volume': volume_str,
                    'volume_spike': volume_spike,
                    'bb_target': bb_target,
                    'change_5m': pct_str,
                    'direction': analysis['direction'],
                    'tv_link': tv_link,
                    'binance_link': binance_link
                })

                self._mark_alerted(scan_result.symbol)
                
                # Telegram rate limit yememek için az bekle
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error in scan cycle: {e}", exc_info=True)

        cycle_duration = (datetime.now() - cycle_start).total_seconds()
        logger.info(f"Cycle completed in {cycle_duration:.1f}s")

    async def run(self):
        """Main async loop."""
        await self.initialize()
        self._running = True

        logger.info(f"Starting main loop (interval: {SCAN_INTERVAL_SECONDS}s)")
        logger.info("Press Ctrl+C to stop\n")

        while self._running:
            try:
                await self.run_scan_cycle()
                
                if self._running:
                    await asyncio.sleep(SCAN_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info("Received cancellation signal")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                await asyncio.sleep(10)

        await self.shutdown()


def handle_shutdown(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    raise KeyboardInterrupt


async def main():
    """Entry point."""
    print("""
╔══════════════════════════════════════════════════════════╗
║     🚀 FUTURES INTELLIGENCE SIGNAL BOT                   ║
║     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                   ║
║     Scanning Binance Futures + On-Chain Intel            ║
╚══════════════════════════════════════════════════════════╝
    """)

    bot = FuturesIntelligenceBot()

    try:
        if sys.platform != 'win32':
            os_signal.signal(os_signal.SIGTERM, handle_shutdown)
            os_signal.signal(os_signal.SIGHUP, handle_shutdown)
    except Exception:
        pass

    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await bot.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
