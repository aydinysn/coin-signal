"""
Signal Manager - Centralized signal storage and distribution
Handles signal persistence and retrieval for the web dashboard.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SignalManager:
    """
    Thread-safe signal manager for storing and retrieving trading signals.
    
    Signals are stored in a JSON file and kept in memory for fast access.
    Automatically maintains a maximum number of signals to prevent unbounded growth.
    """
    
    def __init__(self, storage_path: str = "data/dashboard_signals.json", max_signals: int = 1000):
        self.storage_path = Path(storage_path)
        self.max_signals = max_signals
        self.signals: List[Dict] = []
        self._lock = Lock()
        
        # Ensure data directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing signals
        self._load_signals()
        logger.info(f"SignalManager initialized with {len(self.signals)} existing signals")
    
    def _load_signals(self) -> None:
        """Load signals from JSON file."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    self.signals = json.load(f)
                logger.info(f"Loaded {len(self.signals)} signals from {self.storage_path}")
            except Exception as e:
                logger.error(f"Failed to load signals: {e}")
                self.signals = []
        else:
            # Dosya yoksa boş liste ile başlat ve dosyayı oluştur
            self.signals = []
            self._save_signals()
            logger.info(f"Created new signal storage at {self.storage_path}")
    
    def _save_signals(self) -> None:
        """Save signals to JSON file."""
        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self.signals, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save signals: {e}")
    
    def add_signal(self, signal: Dict) -> None:
        """
        Add a new signal to the storage.
        
        Args:
            signal: Dictionary containing signal data (coin, price, emoji, etc.)
        """
        with self._lock:
            # Add timestamp if not present
            if 'timestamp' not in signal:
                signal['timestamp'] = datetime.now().isoformat()
            
            # Add unique ID
            signal['id'] = len(self.signals) + 1
            
            # Add to beginning of list (newest first)
            self.signals.insert(0, signal)
            
            # Trim to max signals
            if len(self.signals) > self.max_signals:
                self.signals = self.signals[:self.max_signals]
            
            # Save to disk
            self._save_signals()
            
            # Send to webhook (Railway dashboard) if configured
            self._send_webhook(signal)
            
            logger.info(f"Added signal: {signal.get('coin', 'UNKNOWN')} - Total: {len(self.signals)}")
    
    def _send_webhook(self, signal: Dict) -> None:
        """Send signal to webhook URL (Railway dashboard)."""
        try:
            from config import WEBHOOK_URL
            import requests
            
            if not WEBHOOK_URL:
                return  # Webhook not configured
            
            response = requests.post(
                WEBHOOK_URL,
                json=signal,
                timeout=5
            )
            
            if response.status_code == 200:
                logger.info(f"📡 Webhook sent: {signal.get('coin')}")
            else:
                logger.warning(f"Webhook failed ({response.status_code}): {signal.get('coin')}")
                
        except Exception as e:
            # Webhook hatası ana işlemi durdurmamalı
            logger.debug(f"Webhook error (non-critical): {e}")
    
    def get_all_signals(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Get all signals, optionally limited.
        
        Args:
            limit: Maximum number of signals to return (newest first)
            
        Returns:
            List of signal dictionaries
        """
        with self._lock:
            if limit is None:
                return self.signals.copy()
            return self.signals[:limit]
    
    def get_latest_signal(self) -> Optional[Dict]:
        """Get the most recent signal."""
        with self._lock:
            return self.signals[0] if self.signals else None
    
    def get_signals_by_coin(self, coin: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Get signals filtered by coin.
        
        Args:
            coin: Coin symbol (e.g., 'BTC')
            limit: Maximum number of signals to return
            
        Returns:
            List of signal dictionaries for the specified coin
        """
        with self._lock:
            filtered = [s for s in self.signals if s.get('coin', '').upper() == coin.upper()]
            if limit:
                return filtered[:limit]
            return filtered
    
    def clear_all_signals(self) -> None:
        """Clear all signals from memory and storage."""
        with self._lock:
            self.signals = []
            self._save_signals()
            logger.info("All signals cleared")
    
    def get_stats(self) -> Dict:
        """Get statistics about stored signals."""
        with self._lock:
            total = len(self.signals)
            if total == 0:
                return {
                    'total': 0,
                    'long_count': 0,
                    'short_count': 0,
                    'coins': []
                }
            
            long_count = sum(1 for s in self.signals if s.get('direction') == 'LONG')
            short_count = sum(1 for s in self.signals if s.get('direction') == 'SHORT')
            coins = list(set(s.get('coin', 'UNKNOWN') for s in self.signals))
            
            return {
                'total': total,
                'long_count': long_count,
                'short_count': short_count,
                'coins': sorted(coins)
            }
    
    def reload_from_disk(self) -> int:
        """
        Reload signals from disk to sync with other processes.
        Returns the number of signals loaded.
        
        This is useful when bot and dashboard run in separate processes.
        """
        with self._lock:
            old_count = len(self.signals)
            self._load_signals()
            
            # Clean up old signals (older than 5 hours)
            self._cleanup_old_signals(hours=5)
            
            new_count = len(self.signals)
            
            if new_count != old_count:
                logger.info(f"Reloaded signals: {old_count} -> {new_count}")
            
            return new_count
    
    def _cleanup_old_signals(self, hours: int = 5) -> int:
        """
        Remove signals older than specified hours.
        
        Args:
            hours: Age threshold in hours (default: 5)
            
        Returns:
            Number of signals removed
        """
        from datetime import datetime, timedelta
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        original_count = len(self.signals)
        
        # Filter signals newer than cutoff
        self.signals = [
            s for s in self.signals
            if self._is_signal_recent(s, cutoff_time)
        ]
        
        removed_count = original_count - len(self.signals)
        
        if removed_count > 0:
            self._save_signals()
            logger.info(f"🗑️ Cleaned up {removed_count} signals older than {hours} hours")
        
        return removed_count
    
    def _is_signal_recent(self, signal: Dict, cutoff_time: datetime) -> bool:
        """Check if signal is newer than cutoff time."""
        try:
            signal_time = datetime.fromisoformat(signal['timestamp'])
            return signal_time > cutoff_time
        except (KeyError, ValueError):
            # If no valid timestamp, keep the signal
            return True


# Test code
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create test signal manager
    manager = SignalManager("data/test_signals.json")
    
    # Add test signal
    test_signal = {
        'coin': 'BTC',
        'emoji': '🟢',
        'price': 95234.56,
        'volume': '300K',
        'volume_spike': 3.2,
        'bb_target': 45234.5678,
        'change_5m': '+%0.85',
        'direction': 'LONG',
        'tv_link': 'https://www.tradingview.com/chart/?symbol=BINANCE%3ABTCUSDT.P',
        'binance_link': 'https://www.binance.com/en/futures/BTCUSDT'
    }
    
    manager.add_signal(test_signal)
    
    # Get all signals
    all_signals = manager.get_all_signals()
    print(f"\n✅ Total signals: {len(all_signals)}")
    
    # Get stats
    stats = manager.get_stats()
    print(f"📊 Stats: {stats}")
