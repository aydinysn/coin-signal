"""
Futures Intelligence Signal Bot - On-Chain Inspector
Analyzes ERC-20 transfers to detect whale/exchange movements.
Now with dynamic token address resolution via DEX Screener.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp

import config
from config import (
    ETHERSCAN_API_KEY,
    ETHERSCAN_API_URL,
    BSCSCAN_API_KEY,
    BSCSCAN_API_URL,
    KNOWN_WALLETS_PATH,
    TRANSFER_LOOKBACK_COUNT,
    LARGE_TRANSFER_USD,
    WHALE_TRANSFER_CONFIDENCE_BOOST,
    LARGE_AMOUNT_CONFIDENCE_BOOST,
    RECENT_ACTIVITY_CONFIDENCE_BOOST,
    TOKEN_ADDRESSES
)

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Trading signal type based on on-chain analysis."""
    LONG = "LONG"
    SHORT = "SHORT"
    VOLATILITY = "VOLATILITY"
    NEUTRAL = "NEUTRAL"


class WalletType(Enum):
    """Classification of known wallets."""
    WHALE = "whale"
    EXCHANGE = "exchange"
    MARKET_MAKER = "market_maker"
    UNKNOWN = "unknown"


@dataclass
class Transfer:
    """Represents an ERC-20 transfer event."""
    tx_hash: str
    from_address: str
    to_address: str
    value: float
    value_usd: float
    timestamp: datetime
    from_type: WalletType = WalletType.UNKNOWN
    to_type: WalletType = WalletType.UNKNOWN
    from_label: str = "Unknown"
    to_label: str = "Unknown"


@dataclass
class OnChainSignal:
    """Result of on-chain analysis."""
    signal_type: SignalType
    confidence_score: int
    evidence: List[str]
    whale_transfers: int = 0
    exchange_deposits: float = 0.0
    exchange_withdrawals: float = 0.0
    market_maker_activity: bool = False
    analyzed_transfers: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def bias_emoji(self) -> str:
        return {
            SignalType.LONG: "🟢",
            SignalType.SHORT: "🔴",
            SignalType.VOLATILITY: "🟡",
            SignalType.NEUTRAL: "⚪"
        }.get(self.signal_type, "⚪")

    @property
    def bias_text(self) -> str:
        return {
            SignalType.LONG: "LONG (Bullish)",
            SignalType.SHORT: "SHORT (Bearish)",
            SignalType.VOLATILITY: "VOLATILITY",
            SignalType.NEUTRAL: "NEUTRAL"
        }.get(self.signal_type, "NEUTRAL")


# =============================================================================
# DYNAMIC TOKEN ADDRESS RESOLVER
# =============================================================================
async def resolve_token_address(
    session: aiohttp.ClientSession,
    symbol: str,
    chain: str = "ethereum"
) -> Tuple[Optional[str], str]:
    """
    Dynamically resolve token contract address.
    
    Strategy:
    1. First check config.py (fast cache)
    2. If not found, query DEX Screener API
    3. Select highest liquidity pair (scam protection)
    
    Args:
        session: aiohttp session for API calls
        symbol: Token symbol (e.g., 'ETH', 'PEPE')
        chain: Target chain ('ethereum' or 'bsc')
        
    Returns:
        Tuple of (address, chain) or (None, chain)
    """
    symbol_clean = symbol.upper().replace("1000", "").replace("1000000", "")
    
    if symbol_clean in TOKEN_ADDRESSES:
        addresses = TOKEN_ADDRESSES[symbol_clean]
        if chain in addresses:
            logger.info(f"✅ {symbol_clean} address found in config (cache hit)")
            return addresses[chain], chain
        for c, addr in addresses.items():
            logger.info(f"✅ {symbol_clean} address found in config ({c})")
            return addr, c

    logger.info(f"🔍 Dynamically resolving {symbol_clean} address via DEX Screener...")
    
    try:
        url = f"https://api.dexscreener.com/latest/dex/search?q={symbol_clean}"
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                logger.warning(f"DEX Screener API error: {response.status}")
                return None, chain
            
            data = await response.json()
            pairs = data.get("pairs", [])
            
            if not pairs:
                logger.warning(f"No pairs found for {symbol_clean}")
                return None, chain

            best_pair = None
            max_liquidity = 0.0
            
            chain_mapping = {
                "ethereum": "ethereum",
                "bsc": "bsc",
                "eth": "ethereum",
                "binance": "bsc"
            }
            target_chain = chain_mapping.get(chain.lower(), chain)

            for pair in pairs:
                pair_chain = pair.get("chainId", "").lower()
                
                if pair_chain == target_chain or (chain == "ethereum" and pair_chain in ["ethereum", "eth"]):
                    liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                    
                    if liquidity > max_liquidity:
                        max_liquidity = liquidity
                        best_pair = pair

            if not best_pair:
                for pair in pairs:
                    liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                    if liquidity > max_liquidity:
                        max_liquidity = liquidity
                        best_pair = pair

            if best_pair and max_liquidity > 50000:
                address = best_pair.get("baseToken", {}).get("address")
                found_chain = best_pair.get("chainId", chain)
                logger.info(
                    f"🎯 Found {symbol_clean}: {address[:16]}... "
                    f"(Liquidity: ${max_liquidity:,.0f}, Chain: {found_chain})"
                )
                return address, found_chain
            else:
                logger.warning(f"No high-liquidity pair for {symbol_clean} (max: ${max_liquidity:,.0f})")
                return None, chain

    except asyncio.TimeoutError:
        logger.error(f"Timeout resolving {symbol_clean}")
        return None, chain
    except Exception as e:
        logger.error(f"Error resolving {symbol_clean}: {e}")
        return None, chain


class OnChainInspector:
    """
    Analyzes on-chain ERC-20 transfers to detect whale/exchange movements.
    
    Signal Logic:
    - Whale -> Exchange = SHORT (selling pressure)
    - Exchange -> Whale = LONG (accumulation)
    - Market Maker activity = VOLATILITY expected
    """

    def __init__(self):
        self.known_wallets: Dict[str, Dict[str, str]] = self._load_known_wallets()
        self._session: Optional[aiohttp.ClientSession] = None
        self._address_cache: Dict[str, Tuple[Optional[str], str]] = {}

    def _load_known_wallets(self) -> Dict[str, Dict[str, str]]:
        """Load known wallet addresses from JSON file."""
        try:
            path = Path(KNOWN_WALLETS_PATH)
            if path.exists():
                with open(path, 'r') as f:
                    data = json.load(f)
                    logger.info(f"Loaded {sum(len(v) for v in data.values())} known wallets")
                    return data
        except Exception as e:
            logger.error(f"Failed to load known wallets: {e}")
        
        return {"whales": {}, "exchanges": {}, "market_makers": {}}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def resolve_address(self, symbol: str, chain: str = "ethereum") -> Tuple[Optional[str], str]:
        """
        Resolve token address with caching.
        
        Args:
            symbol: Token symbol
            chain: Target blockchain
            
        Returns:
            Tuple of (address, chain)
        """
        cache_key = f"{symbol}_{chain}"
        if cache_key in self._address_cache:
            return self._address_cache[cache_key]
        
        session = await self._get_session()
        result = await resolve_token_address(session, symbol, chain)
        self._address_cache[cache_key] = result
        return result

    def _classify_wallet(self, address: str) -> Tuple[WalletType, str]:
        """
        Classify a wallet address based on known_wallets.json.
        
        Returns:
            Tuple of (WalletType, label)
        """
        addr_lower = address.lower()
        
        for addr, label in self.known_wallets.get("whales", {}).items():
            if addr.lower() == addr_lower:
                return WalletType.WHALE, label
        
        for addr, label in self.known_wallets.get("exchanges", {}).items():
            if addr.lower() == addr_lower:
                return WalletType.EXCHANGE, label
        
        for addr, label in self.known_wallets.get("market_makers", {}).items():
            if addr.lower() == addr_lower:
                return WalletType.MARKET_MAKER, label
        
        return WalletType.UNKNOWN, "Unknown"

    # -------------------------------------------------------------
    # GÜNCELLENMİŞ TRANSFER ÇEKME FONKSİYONU (SOLANA DESTEKLİ)
    # -------------------------------------------------------------
    async def fetch_recent_transfers(
        self,
        token_address: str,
        chain: str = "ethereum",
        limit: int = TRANSFER_LOOKBACK_COUNT
    ) -> List[Transfer]:
        """
        Fetch transfers from EVM chains (Etherscan) AND Solana (Solscan).
        """
        chain_key = chain.lower()

        # >>> SOLANA YÖNLENDİRMESİ <<<
        if chain_key == "solana":
            return await self.fetch_solana_transfers(token_address, limit)

        # ... EVM (Ethereum/BSC/Base vs) MANTIĞI ...
        # Etherscan V2 için Chain ID Haritası
        CHAIN_MAP = {
            "ethereum": "1", "eth": "1",
            "bsc": "56", "binance": "56",
            "base": "8453", "avalanche": "43114", "avax": "43114",
            "polygon": "137", "arbitrum": "42161", "optimism": "10", "fantom": "250"
        }

        if chain_key not in CHAIN_MAP:
            logger.info(f"⏭️ Skipping {chain} (Not supported yet)")
            return []

        chain_id = CHAIN_MAP[chain_key]
        api_url = ETHERSCAN_API_URL
        api_key = ETHERSCAN_API_KEY

        params = {
            "chainid": chain_id,
            "module": "account",
            "action": "tokentx",
            "contractaddress": token_address,
            "page": 1,
            "offset": limit,
            "sort": "desc",
            "apikey": api_key
        }

        try:
            session = await self._get_session()
            async with session.get(api_url, params=params, timeout=30) as resp:
                if resp.status != 200: return []
                data = await resp.json()
                
                if data.get("status") != "1": return []
                
                transfers = []
                for tx in data.get("result", []):
                    try:
                        decimals = int(tx.get("tokenDecimal", 18))
                        value = int(tx.get("value", 0)) / (10 ** decimals)
                        timestamp = datetime.fromtimestamp(int(tx.get("timeStamp", 0)))
                        
                        from_type, from_label = self._classify_wallet(tx.get("from", ""))
                        to_type, to_label = self._classify_wallet(tx.get("to", ""))
                        
                        transfers.append(Transfer(
                            tx_hash=tx.get("hash", ""),
                            from_address=tx.get("from", ""),
                            to_address=tx.get("to", ""),
                            value=value,
                            value_usd=0,
                            timestamp=timestamp,
                            from_type=from_type,
                            to_type=to_type,
                            from_label=from_label,
                            to_label=to_label
                        ))
                    except: continue
                
                logger.info(f"Fetched {len(transfers)} transfers for {token_address[:10]}... (Chain: {chain})")
                return transfers
        except Exception as e:
            logger.error(f"EVM Fetch Error: {e}")
            return []

    # -------------------------------------------------------------
    # YENİ EKLENEN: SOLANA ÖZEL FONKSİYONU
    # -------------------------------------------------------------
    async def fetch_solana_transfers(self, token_address: str, limit: int = 50) -> List[Transfer]:
        """
        Fetch Solana SPL token transfers via Solscan Public API.
        """
        # Solscan Public API Endpoint
        url = f"https://public-api.solscan.io/transfer/token?token_address={token_address}&limit={limit}&offset=0"
        
        try:
            session = await self._get_session()
            # Solana API bazen yavaştır, timeout uzun tutuldu
            async with session.get(url, timeout=20) as resp:
                if resp.status == 429:
                    logger.warning("⚠️ Solscan Rate Limit (Too many requests). Skipping Solana for this cycle.")
                    return []
                if resp.status != 200:
                    logger.error(f"Solscan API Error: {resp.status}")
                    return []

                data = await resp.json()
                # Solscan yapısı farklıdır: {'data': [...]}
                tx_list = data.get("data", [])
                
                transfers = []
                for tx in tx_list:
                    try:
                        # Solana'da decimal genelde API'den gelir veya 9'dur (SOL)
                        decimals = int(tx.get("tokenDecimals", 9))
                        amount_raw = int(tx.get("amount", 0))
                        value = amount_raw / (10 ** decimals)
                        
                        # Zaman damgası (Unix)
                        timestamp = datetime.fromtimestamp(tx.get("blockTime", 0))
                        
                        from_addr = tx.get("fromUserAccount", "")
                        to_addr = tx.get("toUserAccount", "")
                        
                        from_type, from_label = self._classify_wallet(from_addr)
                        to_type, to_label = self._classify_wallet(to_addr)

                        transfers.append(Transfer(
                            tx_hash=tx.get("_id", ""),
                            from_address=from_addr,
                            to_address=to_addr,
                            value=value,
                            value_usd=0,
                            timestamp=timestamp,
                            from_type=from_type,
                            to_type=to_type,
                            from_label=from_label,
                            to_label=to_label
                        ))
                    except Exception as e:
                        continue
                
                logger.info(f"🌞 Fetched {len(transfers)} SOLANA transfers for {token_address[:10]}...")
                return transfers

        except Exception as e:
            logger.error(f"Solana Fetch Error: {e}")
            return []

    def analyze_transfers(
        self,
        transfers: List[Transfer],
        current_price: float = 0
    ) -> OnChainSignal:
        """
        Analyze transfers to determine signal and confidence.
        
        Args:
            transfers: List of Transfer objects
            current_price: Current token price for USD calculations
            
        Returns:
            OnChainSignal with signal type and confidence
        """
        if not transfers:
            return OnChainSignal(
                signal_type=SignalType.NEUTRAL,
                confidence_score=0,
                evidence=["No transfer data available"],
                analyzed_transfers=0
            )

        evidence = []
        base_confidence = 50
        
        whale_to_exchange_count = 0
        whale_to_exchange_value = 0.0
        exchange_to_whale_count = 0
        exchange_to_whale_value = 0.0
        market_maker_moves = 0
        recent_whale_activity = 0

        one_hour_ago = datetime.now() - timedelta(hours=1)

        for transfer in transfers:
            if current_price > 0:
                transfer.value_usd = transfer.value * current_price

            if transfer.from_type == WalletType.WHALE and transfer.to_type == WalletType.EXCHANGE:
                whale_to_exchange_count += 1
                whale_to_exchange_value += transfer.value_usd or transfer.value
                evidence.append(
                    f"🔴 {transfer.from_label} → {transfer.to_label}: "
                    f"${transfer.value_usd:,.0f}" if transfer.value_usd else f"{transfer.value:,.2f} tokens"
                )

            elif transfer.from_type == WalletType.EXCHANGE and transfer.to_type == WalletType.WHALE:
                exchange_to_whale_count += 1
                exchange_to_whale_value += transfer.value_usd or transfer.value
                evidence.append(
                    f"🟢 {transfer.from_label} → {transfer.to_label}: "
                    f"${transfer.value_usd:,.0f}" if transfer.value_usd else f"{transfer.value:,.2f} tokens"
                )

            if transfer.from_type == WalletType.MARKET_MAKER or transfer.to_type == WalletType.MARKET_MAKER:
                market_maker_moves += 1

            if transfer.from_type == WalletType.WHALE or transfer.to_type == WalletType.WHALE:
                if transfer.timestamp > one_hour_ago:
                    recent_whale_activity += 1

        confidence = base_confidence
        confidence += min(whale_to_exchange_count * WHALE_TRANSFER_CONFIDENCE_BOOST, 40)
        confidence += min(exchange_to_whale_count * WHALE_TRANSFER_CONFIDENCE_BOOST, 40)
        
        large_threshold = LARGE_TRANSFER_USD
        if whale_to_exchange_value > large_threshold or exchange_to_whale_value > large_threshold:
            confidence += LARGE_AMOUNT_CONFIDENCE_BOOST
        
        if recent_whale_activity > 0:
            confidence += min(recent_whale_activity * RECENT_ACTIVITY_CONFIDENCE_BOOST, 20)

        confidence = min(confidence, 95)

        if market_maker_moves >= 3:
            signal_type = SignalType.VOLATILITY
            evidence.insert(0, f"⚠️ High Market Maker activity detected ({market_maker_moves} moves)")
        elif whale_to_exchange_count > exchange_to_whale_count:
            signal_type = SignalType.SHORT
            evidence.insert(0, f"📉 {whale_to_exchange_count} whale deposits to exchanges detected")
        elif exchange_to_whale_count > whale_to_exchange_count:
            signal_type = SignalType.LONG
            evidence.insert(0, f"📈 {exchange_to_whale_count} whale withdrawals from exchanges detected")
        elif whale_to_exchange_count == exchange_to_whale_count and whale_to_exchange_count > 0:
            signal_type = SignalType.VOLATILITY
        else:
            signal_type = SignalType.NEUTRAL
            confidence = max(confidence - 30, 20)

        return OnChainSignal(
            signal_type=signal_type,
            confidence_score=confidence,
            evidence=evidence[:5],
            whale_transfers=whale_to_exchange_count + exchange_to_whale_count,
            exchange_deposits=whale_to_exchange_value,
            exchange_withdrawals=exchange_to_whale_value,
            market_maker_activity=market_maker_moves > 0,
            analyzed_transfers=len(transfers)
        )

    async def inspect(
        self,
        token_address: str,
        chain: str = "ethereum",
        current_price: float = 0
    ) -> OnChainSignal:
        """
        Full inspection pipeline: fetch transfers and analyze.
        
        Args:
            token_address: ERC-20 contract address
            chain: 'ethereum' or 'bsc'
            current_price: Current token price
            
        Returns:
            OnChainSignal with complete analysis
        """
        transfers = await self.fetch_recent_transfers(token_address, chain)
        return self.analyze_transfers(transfers, current_price)

    async def inspect_by_symbol(
        self,
        symbol: str,
        chain: str = "ethereum",
        current_price: float = 0
    ) -> OnChainSignal:
        """
        Full inspection by symbol with dynamic address resolution.
        
        Args:
            symbol: Token symbol (e.g., 'ETH', 'PEPE')
            chain: Target blockchain
            current_price: Current token price
            
        Returns:
            OnChainSignal with complete analysis
        """
        token_address, resolved_chain = await self.resolve_address(symbol, chain)
        
        if not token_address:
            logger.warning(f"❌ No contract address found for {symbol}, skipping on-chain analysis")
            return OnChainSignal(
                signal_type=SignalType.NEUTRAL,
                confidence_score=30,
                evidence=[f"No contract address available for {symbol}"],
                analyzed_transfers=0
            )
        
        return await self.inspect(token_address, resolved_chain, current_price)


async def test_inspector():
    """Test the inspector with dynamic address resolution."""
    logging.basicConfig(level=logging.INFO)
    
    test_symbols = ["ETH", "PEPE", "SHIB", "DOGE"]
    
    async with OnChainInspector() as inspector:
        for symbol in test_symbols:
            print(f"\n{'='*60}")
            print(f"🔍 ON-CHAIN ANALYSIS: {symbol}")
            print(f"{'='*60}")
            
            signal = await inspector.inspect_by_symbol(symbol, "ethereum", current_price=0)
            
            print(f"Signal: {signal.bias_emoji} {signal.bias_text}")
            print(f"Confidence: {signal.confidence_score}%")
            print(f"Transfers Analyzed: {signal.analyzed_transfers}")
            
            if signal.evidence:
                print("Evidence:")
                for e in signal.evidence:
                    print(f"  • {e}")
            
            await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(test_inspector())
