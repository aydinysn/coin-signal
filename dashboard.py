"""
Web Dashboard - Flask Application
Provides REST API and WebSocket for real-time signal monitoring.
"""

import logging
from flask import Flask, render_template, jsonify, send_from_directory, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from signal_manager import SignalManager
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, 
            static_folder='static',
            template_folder='static')
app.config['SECRET_KEY'] = 'scalp-trade-dashboard-secret'
CORS(app)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize Signal Manager
signal_manager = SignalManager()


@app.route('/')
def index():
    """Serve the main dashboard page."""
    return send_from_directory('static', 'index.html')


@app.route('/api/signals')
def get_signals():
    """REST API: Get all signals."""
    try:
        limit = request.args.get('limit', type=int)
        signals = signal_manager.get_all_signals(limit=limit)
        return jsonify({
            'success': True,
            'signals': signals,
            'count': len(signals)
        })
    except Exception as e:
        logger.error(f"Error getting signals: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/signals/latest')
def get_latest_signal():
    """REST API: Get the most recent signal."""
    try:
        signal = signal_manager.get_latest_signal()
        return jsonify({
            'success': True,
            'signal': signal
        })
    except Exception as e:
        logger.error(f"Error getting latest signal: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stats')
def get_stats():
    """REST API: Get signal statistics."""
    try:
        stats = signal_manager.get_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection."""
    logger.info('Client connected')
    emit('connection_response', {'status': 'connected'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    logger.info('Client disconnected')


@socketio.on('request_signals')
def handle_request_signals():
    """Handle request for all signals via WebSocket."""
    signals = signal_manager.get_all_signals()
    emit('signals_data', {'signals': signals})


def broadcast_new_signal(signal):
    """
    Broadcast a new signal to all connected clients.
    Call this function when a new signal is added.
    """
    socketio.emit('new_signal', {'signal': signal}, broadcast=True)
    logger.info(f"Broadcasted new signal: {signal.get('coin', 'UNKNOWN')}")


def run_dashboard(host='127.0.0.1', port=5000, debug=False):
    """
    Run the Flask dashboard server.
    
    Args:
        host: Host address (default: localhost)
        port: Port number (default: 5000)
        debug: Enable debug mode
    """
    # Start background thread to reload signals periodically
    import threading
    import time
    
    def reload_signals_loop():
        """Background thread to reload signals from disk every 5 seconds."""
        previous_count = 0
        while True:
            time.sleep(5)
            try:
                # Reload from disk
                current_count = signal_manager.reload_from_disk()
                
                # Broadcast to all connected clients if signals changed
                if current_count != previous_count:
                    signals = signal_manager.get_all_signals()
                    socketio.emit('signals_data', {'signals': signals})
                    logger.info(f"📡 Broadcasted {current_count} signals to clients")
                    previous_count = current_count
                    
            except Exception as e:
                logger.error(f"Error reloading signals: {e}")
    
    reload_thread = threading.Thread(target=reload_signals_loop, daemon=True)
    reload_thread.start()
    logger.info("✅ Auto-reload thread started (checks every 5s)")
    
    logger.info(f"🚀 Starting dashboard on http://{host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════════════════════╗
║     📊 TRADING SIGNAL DASHBOARD                          ║
║     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                   ║
║     Real-time signal monitoring via web browser          ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Cloud deployment (Railway, Render, etc.) için PORT env variable kullan
    import os
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'  # Production'da debug=False
    run_dashboard(host='0.0.0.0', port=port, debug=debug)

