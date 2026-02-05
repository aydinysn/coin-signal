"""
Futures Intelligence Signal Bot - Market Scanner
Scans Binance Futures for volume spikes and price momentum.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import ccxt.async_support as ccxt

from config import (
    VOLUME_SPIKE_MULTIPLIER,
    PRICE_CHANGE_THRESHOLD,
    MIN_VOLUME_USD_5M,
    TOKEN_ADDRESSES
)

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Represents a detected trading opportunity."""
    symbol: str
    base_asset: str
    current_price: float
    price_change_1h: float
    volume_5m: float
    volume_usd_5m: float  # USD değeri ekledik
    avg_volume_1h: float
    volume_spike_ratio: float
    trigger_reason: str
    token_address: Optional[str] = None
    chain: str = "ethereum"
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_volume_spike(self) -> bool:
        return self.volume_spike_ratio >= VOLUME_SPIKE_MULTIPLIER

    @property
    def is_price_momentum(self) -> bool:
        return abs(self.price_change_1h) >= PRICE_CHANGE_THRESHOLD


class BinanceFuturesScanner:
    """
    Scans Binance USDT-M Futures for significant trading opportunities.
    
    Filters:
    - Min 5m volume: $100K USD (noise reduction)
    - Volume spikes: 5m volume > 5x average
    - Price momentum: 1h change > 4%
    """

    def __init__(self):
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True
            }
        })
        self._pairs_cache: List[str] = []
        self._cache_time: Optional[datetime] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close the exchange connection."""
        await self.exchange.close()

    async def fetch_usdt_futures_pairs(self, force_refresh: bool = False) -> List[str]:
        """
        Fetch all USDT-M perpetual futures symbols.
        
        Args:
            force_refresh: Bypass cache and fetch fresh data.
            
        Returns:
            List of trading pair symbols (e.g., ['BTC/USDT', 'ETH/USDT'])
        """
        if (
            not force_refresh
            and self._pairs_cache
            and self._cache_time
            and (datetime.now() - self._cache_time).seconds < 3600
        ):
            return self._pairs_cache

        try:
            markets = await self.exchange.load_markets()
            usdt_pairs = [
                symbol for symbol, market in markets.items()
                if (
                    market.get('quote') == 'USDT'
                    and market.get('swap', False)
                    and market.get('active', True)
                    and ':USDT' in symbol
                )
            ]
            self._pairs_cache = usdt_pairs
            self._cache_time = datetime.now()
            logger.info(f"Loaded {len(usdt_pairs)} USDT-M futures pairs")
            return usdt_pairs

        except Exception as e:
            logger.error(f"Failed to fetch futures pairs: {e}")
            return self._pairs_cache if self._pairs_cache else []

    async def _fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '5m',
        limit: int = 12
    ) -> List:
        """Fetch OHLCV candles for a symbol."""
        try:
            ohlcv = await self.exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                limit=limit
            )
            return ohlcv
        except Exception as e:
            logger.debug(f"Failed to fetch OHLCV for {symbol}: {e}")
            return []

    async def _fetch_ticker(self, symbol: str) -> Optional[Dict]:
        """Fetch 24h ticker data for a symbol."""
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            logger.debug(f"Failed to fetch ticker for {symbol}: {e}")
            return None

    def _get_token_address(self, base_asset: str) -> tuple[Optional[str], str]:
        """
        Get token contract address for on-chain analysis.
        
        Returns:
            Tuple of (address, chain) or (None, 'unknown')
        """
        asset_upper = base_asset.upper()
        if asset_upper in TOKEN_ADDRESSES:
            addresses = TOKEN_ADDRESSES[asset_upper]
            if 'ethereum' in addresses:
                return addresses['ethereum'], 'ethereum'
            elif 'bsc' in addresses:
                return addresses['bsc'], 'bsc'
        return None, 'unknown'

    async def analyze_pair(self, symbol: str) -> Optional[ScanResult]:
        """
        Analyze a single trading pair for opportunities.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT:USDT')
            
        Returns:
            ScanResult if opportunity detected, None otherwise.
        """
        ohlcv_task = self._fetch_ohlcv(symbol, '5m', 12)
        ticker_task = self._fetch_ticker(symbol)
        
        ohlcv, ticker = await asyncio.gather(ohlcv_task, ticker_task)

        if not ohlcv or len(ohlcv) < 2 or not ticker:
            return None

        volumes = [candle[5] for candle in ohlcv]
        current_volume = volumes[-1] if volumes else 0
        avg_volume = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 1
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        current_price = ticker.get('last', 0)
        price_change_pct = ticker.get('percentage', 0) or 0
        
        # Calculate 5m volume in USD for filtering
        volume_5m_usd = current_volume * current_price if current_price > 0 else 0
        
        # Filter: Minimum volume threshold (noise reduction)
        if volume_5m_usd < MIN_VOLUME_USD_5M:
            return None

        is_volume_spike = volume_ratio >= VOLUME_SPIKE_MULTIPLIER
        is_price_momentum = abs(price_change_pct) >= PRICE_CHANGE_THRESHOLD

        if not (is_volume_spike or is_price_momentum):
            return None

        triggers = []
        if is_volume_spike:
            triggers.append(f"Volume Spike: {volume_ratio:.1f}x")
        if is_price_momentum:
            direction = "📈" if price_change_pct > 0 else "📉"
            triggers.append(f"Price {direction}: {price_change_pct:+.2f}%")

        base_asset = symbol.split('/')[0]
        token_address, chain = self._get_token_address(base_asset)

        return ScanResult(
            symbol=symbol,
            base_asset=base_asset,
            current_price=current_price,
            price_change_1h=price_change_pct,
            volume_5m=current_volume,
            volume_usd_5m=volume_5m_usd,  # USD değerini ekliyoruz
            avg_volume_1h=avg_volume,
            volume_spike_ratio=volume_ratio,
            trigger_reason=" | ".join(triggers),
            token_address=token_address,
            chain=chain
        )

    async def scan(
        self,
        symbols: Optional[List[str]] = None,
        max_concurrent: int = 10
    ) -> List[ScanResult]:
        """
        Scan all or specified symbols for opportunities.
        
        Args:
            symbols: Optional list of symbols to scan. If None, scans all.
            max_concurrent: Maximum concurrent API calls.
            
        Returns:
            List of detected opportunities.
        """
        if symbols is None:
            symbols = await self.fetch_usdt_futures_pairs()

        if not symbols:
            logger.warning("No symbols to scan")
            return []

        logger.info(f"Scanning {len(symbols)} futures pairs...")
        results: List[ScanResult] = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_with_limit(sym: str) -> Optional[ScanResult]:
            async with semaphore:
                return await self.analyze_pair(sym)

        tasks = [analyze_with_limit(sym) for sym in symbols]
        scan_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in scan_results:
            if isinstance(result, ScanResult):
                results.append(result)
            elif isinstance(result, Exception):
                logger.debug(f"Scan error: {result}")

        results.sort(key=lambda x: x.volume_spike_ratio, reverse=True)

        logger.info(f"Found {len(results)} opportunities")
        return results


async def test_scanner():
    """Test the scanner with live data."""
    logging.basicConfig(level=logging.INFO)
    
    async with BinanceFuturesScanner() as scanner:
        results = await scanner.scan()
        
        print(f"\n{'='*60}")
        print(f"📊 SCAN RESULTS: {len(results)} Opportunities Detected")
        print(f"{'='*60}\n")
        
        for r in results[:10]:
            print(f"🎯 {r.symbol}")
            print(f"   Price: ${r.current_price:,.4f} ({r.price_change_1h:+.2f}%)")
            print(f"   Volume Spike: {r.volume_spike_ratio:.1f}x")
            print(f"   Trigger: {r.trigger_reason}")
            if r.token_address:
                print(f"   Token: {r.token_address[:20]}... ({r.chain})")
            print()


if __name__ == "__main__":
    asyncio.run(test_scanner())
