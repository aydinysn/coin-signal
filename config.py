"""
Futures Intelligence Signal Bot - Configuration
Optimized for high-quality signals and noise reduction.
"""

import os
from typing import Dict

# =============================================================================
# TELEGRAM CONFIGURATION
# =============================================================================
# .env dosyasından okur, yoksa varsayılan değeri kullanır.
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "7653317241:AAHnXALHtsqABZJJh1zvKt7cvb64v9V-l2w")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "-1003740980293")

# =============================================================================
# BLOCKCHAIN RPC ENDPOINTS
# =============================================================================
ETH_RPC_URL: str = os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com")
BSC_RPC_URL: str = os.getenv("BSC_RPC_URL", "https://bsc-dataseed1.binance.org")

# =============================================================================
# BLOCKCHAIN EXPLORER APIs
# =============================================================================
ETHERSCAN_API_KEY: str = os.getenv("ETHERSCAN_API_KEY", "AT86BA77Y9E5TTP4R43YFDRN4SH1WMT4QG")
BSCSCAN_API_KEY: str = os.getenv("BSCSCAN_API_KEY", "AT86BA77Y9E5TTP4R43YFDRN4SH1WMT4QG")

ETHERSCAN_API_URL: str = "https://api.etherscan.io/v2/api"
BSCSCAN_API_URL: str = "https://api.etherscan.io/v2/api"
# Not: Artık ikisi de aynı V2 adresine gidiyor, farkı "chainid" parametresiyle yapacağız.

# =============================================================================
# SCANNER THRESHOLDS (NOISE REDUCTION SETTINGS)
# =============================================================================
# Hacim en az 5 katına çıkmalı (Eski değer: 2.0 -> Çok gürültülüydü)
VOLUME_SPIKE_MULTIPLIER: float = 5.0  

# Fiyat en az %4 oynamalı (Eski değer: 3.0)
PRICE_CHANGE_THRESHOLD: float = 4.0   

# Çok düşük hacimli coinleri görmezden gel (Min 5 dakikalık hacim $)
MIN_VOLUME_USD_5M: float = 100_000.0  

# Tarama sıklığı (Saniye). 30 saniye API limitleri için idealdir.
SCAN_INTERVAL_SECONDS: int = 30       

# =============================================================================
# ON-CHAIN INSPECTOR SETTINGS
# =============================================================================
TRANSFER_LOOKBACK_COUNT: int = 50         # Son 50 transferi analiz et
LARGE_TRANSFER_USD: float = 1_000_000     # 1 Milyon $ altı transferleri "Balina" sayma
WHALE_TRANSFER_CONFIDENCE_BOOST: int = 20 # Balina tespit edilirse güven skorunu %20 artır
LARGE_AMOUNT_CONFIDENCE_BOOST: int = 15   # Büyük miktar için %15 artır
RECENT_ACTIVITY_CONFIDENCE_BOOST: int = 10 # Son 1 saatte olduysa %10 artır

# =============================================================================
# TOKEN ADDRESS MAPPINGS (Symbol -> ERC-20/BEP-20 Contract Address)
# =============================================================================
# Sadece Vadeli İşlemlerde en çok hacmi olan MAJOR coinler
TOKEN_ADDRESSES: Dict[str, Dict[str, str]] = {
    "ETH": {
        "ethereum": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
        "bsc": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8"        # ETH on BSC
    },
    "BTC": {
        "ethereum": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # WBTC
        "bsc": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c"        # BTCB
    },
    "BNB": {
        "bsc": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"        # WBNB
    },
    "SOL": {
        "ethereum": "0xD31a59c85aE9D8edEFeC411D448f90841571b89c",  # Wrapped SOL
    },
    "LINK": {
        "ethereum": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
        "bsc": "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD"
    },
    "UNI": {
        "ethereum": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"
    },
    "AAVE": {
        "ethereum": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"
    },
    "DOGE": {
        "bsc": "0xbA2aE424d960c26247Dd6c32edC70B295c744C43"
    },
    "XRP": {
        "bsc": "0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE"
    },
    "ADA": {
        "bsc": "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47"
    },
    "AVAX": {
        "ethereum": "0x85f138bfEE4ef8e540890CFb48F620571d67Eda3"
    },
    "SHIB": {
        "ethereum": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE"
    },
    "PEPE": {
        "ethereum": "0x6982508145454Ce325dDbE47a25d4ec3d2311933"
    }
}

# =============================================================================
# KNOWN WALLETS FILE PATH
# =============================================================================
KNOWN_WALLETS_PATH: str = "data/known_wallets.json"

# =============================================================================
# WEB DASHBOARD SETTINGS
# =============================================================================
DASHBOARD_ENABLED: bool = True        # Enable web dashboard
DASHBOARD_HOST: str = "127.0.0.1"     # Dashboard host (localhost)
DASHBOARD_PORT: int = 5000             # Dashboard port
DASHBOARD_MAX_SIGNALS: int = 1000      # Maximum signals to keep (auto-cleanup after 5 hours)

# =============================================================================
# LOGGING
# =============================================================================
LOG_LEVEL: str = "INFO"
LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"