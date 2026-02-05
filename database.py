"""
Database Module - PostgreSQL Connection and Operations
Manages signal storage in PostgreSQL database.
"""

import logging
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

logger = logging.getLogger(__name__)


class Database:
    """PostgreSQL Database Manager for Signal Storage"""
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database connection.
        
        Args:
            database_url: PostgreSQL connection string (from env if not provided)
        """
        self.database_url = database_url or os.environ.get('DATABASE_URL')
        
        if not self.database_url:
            raise ValueError("DATABASE_URL not provided and not found in environment variables")
        
        # Create connection pool
        try:
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                1,  # Min connections
                10,  # Max connections
                self.database_url
            )
            logger.info("✅ PostgreSQL connection pool created")
            
            # Initialize database schema
            self._init_schema()
            
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}")
            raise
    
    def _get_connection(self):
        """Get a connection from the pool."""
        return self.connection_pool.getconn()
    
    def _return_connection(self, conn):
        """Return a connection to the pool."""
        self.connection_pool.putconn(conn)
    
    def _init_schema(self):
        """Initialize database schema if not exists."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Create signals table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS signals (
                        id SERIAL PRIMARY KEY,
                        coin VARCHAR(20) NOT NULL,
                        emoji VARCHAR(10),
                        price DECIMAL(20, 8),
                        volume VARCHAR(20),
                        volume_spike DECIMAL(10, 2),
                        bb_target DECIMAL(20, 8),
                        change_5m VARCHAR(20),
                        direction VARCHAR(10),
                        tv_link TEXT,
                        binance_link TEXT,
                        timestamp TIMESTAMP DEFAULT NOW(),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                
                # Create indexes
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_signals_timestamp 
                    ON signals(timestamp DESC)
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_signals_coin 
                    ON signals(coin)
                """)
                
                conn.commit()
                logger.info("✅ Database schema initialized")
                
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to initialize schema: {e}")
            raise
        finally:
            self._return_connection(conn)
    
    def add_signal(self, signal: Dict) -> bool:
        """
        Add a new signal to the database.
        
        Args:
            signal: Signal dictionary
            
        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO signals (
                        coin, emoji, price, volume, volume_spike,
                        bb_target, change_5m, direction, tv_link, binance_link, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    signal.get('coin'),
                    signal.get('emoji'),
                    signal.get('price'),
                    signal.get('volume'),
                    signal.get('volume_spike'),
                    signal.get('bb_target'),
                    signal.get('change_5m'),
                    signal.get('direction'),
                    signal.get('tv_link'),
                    signal.get('binance_link'),
                    signal.get('timestamp', datetime.now().isoformat())
                ))
                conn.commit()
                logger.info(f"✅ Signal added to database: {signal.get('coin')}")
                return True
                
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add signal: {e}")
            return False
        finally:
            self._return_connection(conn)
    
    def get_all_signals(self, limit: int = 1000) -> List[Dict]:
        """
        Get all signals from the database.
        
        Args:
            limit: Maximum number of signals to retrieve
            
        Returns:
            List of signal dictionaries
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM signals 
                    ORDER BY timestamp DESC 
                    LIMIT %s
                """, (limit,))
                
                signals = cur.fetchall()
                
                # Convert to regular dicts and format
                return [dict(signal) for signal in signals]
                
        except Exception as e:
            logger.error(f"Failed to get signals: {e}")
            return []
        finally:
            self._return_connection(conn)
    
    def get_recent_signals(self, hours: int = 5) -> List[Dict]:
        """
        Get signals from the last N hours.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            List of signal dictionaries
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cutoff_time = datetime.now() - timedelta(hours=hours)
                
                cur.execute("""
                    SELECT * FROM signals 
                    WHERE timestamp >= %s 
                    ORDER BY timestamp DESC
                """, (cutoff_time,))
                
                signals = cur.fetchall()
                return [dict(signal) for signal in signals]
                
        except Exception as e:
            logger.error(f"Failed to get recent signals: {e}")
            return []
        finally:
            self._return_connection(conn)
    
    def cleanup_old_signals(self, hours: int = 5) -> int:
        """
        Delete signals older than N hours.
        
        Args:
            hours: Number of hours threshold
            
        Returns:
            Number of deleted signals
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cutoff_time = datetime.now() - timedelta(hours=hours)
                
                cur.execute("""
                    DELETE FROM signals 
                    WHERE timestamp < %s
                """, (cutoff_time,))
                
                deleted_count = cur.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"🗑️ Deleted {deleted_count} old signals")
                
                return deleted_count
                
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to cleanup old signals: {e}")
            return 0
        finally:
            self._return_connection(conn)
    
    def get_signal_count(self) -> int:
        """Get total number of signals in database."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM signals")
                count = cur.fetchone()[0]
                return count
        except Exception as e:
            logger.error(f"Failed to get signal count: {e}")
            return 0
        finally:
            self._return_connection(conn)
    
    def close(self):
        """Close all database connections."""
        if hasattr(self, 'connection_pool'):
            self.connection_pool.closeall()
            logger.info("🔌 Database connections closed")
