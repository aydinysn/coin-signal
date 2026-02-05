"""
Analyzer Module - Simplified Bollinger Band Analysis
Calculates direction and Bollinger Bands for simple messaging
"""

import pandas as pd
import ccxt.async_support as ccxt


def calculate_bollinger_bands(prices, period=20, std_dev=2):
    """
    Manuel Bollinger Band hesaplaması.
    
    Args:
        prices: Pandas Series of closing prices
        period: MA period (default 20)
        std_dev: Standard deviation multiplier (default 2)
        
    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    # Basit Hareketli Ortalama (SMA)
    sma = prices.rolling(window=period, min_periods=period).mean()
    
    # Standart Sapma
    std = prices.rolling(window=period, min_periods=period).std()
    
    # Bollinger Bantları
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    
    return upper_band.iloc[-1], sma.iloc[-1], lower_band.iloc[-1]


async def get_advanced_analysis(exchange, symbol: str):
    """
    Basitleştirilmiş analiz: Yön + Bollinger Band + 5dk değişim.
    
    Args:
        exchange: CCXT exchange instance
        symbol: Trading pair symbol (e.g., 'BTC/USDT')
        
    Returns:
        Dict with symbol, price, direction, BB levels, and 5m change
    """
    try:
        # 1. Ana Analiz Verisi (15 Dakikalık - Trend ve BB için)
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        
        if not ohlcv or len(ohlcv) < 25:
            return None
            
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        current_price = df['close'].iloc[-1]
        
        # 2. Bollinger Bantlarını Hesapla (20 mumluk, 2 standart sapma)
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(df['close'], period=20, std_dev=2)

        # 3. 5 Dakikalık Değişim Verisi
        ohlcv_5m = await exchange.fetch_ohlcv(symbol, timeframe='5m', limit=2)
        
        if not ohlcv_5m or len(ohlcv_5m) < 2:
            # 5dk verisi yoksa, mevcut mumdan tahmini yap
            change_5m_pct = 0.0
        else:
            df_5m = pd.DataFrame(ohlcv_5m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Son 5 dakikalık mumun değişimi: (Kapanış - Açılış) / Açılış
            last_5m_open = df_5m['open'].iloc[-1]
            last_5m_close = df_5m['close'].iloc[-1]
            change_5m_pct = ((last_5m_close - last_5m_open) / last_5m_open) * 100

        # 4. Yön Tayini (5 Dakikalık Değişime Göre)
        # Artık 5dk değişimi kullanıyoruz, böylece direction ile change_5m uyumlu olur
        direction = "LONG" if change_5m_pct > 0 else "SHORT"

        return {
            "symbol": symbol,
            "price": current_price,
            "direction": direction,
            "bb_upper": bb_upper,    # Üst bant
            "bb_middle": bb_middle,  # Orta (SMA)
            "bb_lower": bb_lower,    # Alt bant
            "change_5m": change_5m_pct  # 5 dakikalık yüzde
        }

    except Exception as e:
        print(f"Analiz hatası {symbol}: {e}")
        return None
