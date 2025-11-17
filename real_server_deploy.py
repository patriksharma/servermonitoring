#!/usr/bin/env python3
"""
REAL SERVER - Tracks Actual User Visits and Metrics
Deploy this to Render.com to test with real data
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
import time
import os
import redis
import hashlib
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# Track server start time
start_time = time.time()

# In-memory storage (for free tier without Redis)
# In production, use Redis for persistence
visit_log = []  # List of {timestamp, user_id}
page_views = defaultdict(int)
transaction_log = []  # List of transaction timestamps

# Try to connect to Redis if available, otherwise use in-memory
try:
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    r = redis.from_url(redis_url, decode_responses=True)
    r.ping()
    USE_REDIS = True
    print("✅ Using Redis for storage")
except:
    r = None
    USE_REDIS = False
    print("⚠️  Using in-memory storage (data resets on restart)")

# ==============================================================================
# REAL METRIC TRACKING FUNCTIONS
# ==============================================================================

def get_user_identifier():
    """Create unique identifier from IP + User Agent"""
    # Use IP address + browser user agent to identify unique users
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()  # Get first IP if multiple
    user_agent = request.headers.get('User-Agent', 'unknown')
    # Create a simple hash to identify unique browser+device combos
    identifier = f"{ip}:{user_agent}"
    user_id = hashlib.md5(identifier.encode()).hexdigest()[:12]
    return user_id

def track_user_visit():
    """Track a real user visit"""
    user_id = get_user_identifier()
    timestamp = time.time()
    
    if USE_REDIS:
        # Store in Redis with 5 minute expiry
        r.hset(f'user:{user_id}', 'last_seen', timestamp)
        r.expire(f'user:{user_id}', 300)  # 5 minutes
    else:
        # Store in memory - update existing user or add new
        # Remove old entries for this user
        visit_log[:] = [v for v in visit_log if v['user_id'] != user_id]
        # Add new entry
        visit_log.append({'timestamp': timestamp, 'user_id': user_id})
        # Clean old visits (older than 5 minutes)
        cutoff = time.time() - 300
        visit_log[:] = [v for v in visit_log if v['timestamp'] > cutoff]

def get_connected_users():
    """Get count of users active in last 5 minutes - REAL"""
    if USE_REDIS:
        count = 0
        for key in r.scan_iter('user:*'):
            count += 1
        return count
    else:
        # Count unique users in last 5 minutes
        cutoff = time.time() - 300
        active_users = set(v['user_id'] for v in visit_log if v['timestamp'] > cutoff)
        return len(active_users)

def track_transaction():
    """Track a real transaction"""
    timestamp = time.time()
    
    if USE_REDIS:
        current_minute = int(timestamp / 60)
        r.incr(f'transactions:{current_minute}')
        r.expire(f'transactions:{current_minute}', 120)
        r.incr('total_transactions')
    else:
        transaction_log.append(timestamp)

def get_transactions_per_minute():
    """Get transactions in last minute - REAL"""
    if USE_REDIS:
        current_minute = int(time.time() / 60)
        return int(r.get(f'transactions:{current_minute}') or 0)
    else:
        # Count transactions in last minute
        cutoff = time.time() - 60
        return sum(1 for t in transaction_log if t > cutoff)

def get_total_transactions():
    """Get total transactions - REAL"""
    if USE_REDIS:
        return int(r.get('total_transactions') or 0)
    else:
        return len(transaction_log)

# ==============================================================================
# ROUTES
# ==============================================================================

@app.route('/')
def home():
    """Homepage - tracks visit"""
    track_user_visit()
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Real Server Monitoring Test</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #2563eb; }
            .metric {
                background: #f0f9ff;
                padding: 20px;
                margin: 15px 0;
                border-radius: 8px;
                border-left: 4px solid #2563eb;
            }
            .metric h3 { margin: 0 0 10px 0; color: #1e40af; }
            .metric p { margin: 5px 0; font-size: 24px; font-weight: bold; color: #1e293b; }
            button {
                background: #2563eb;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 16px;
                margin: 10px 5px;
            }
            button:hover { background: #1d4ed8; }
            .info {
                background: #fef3c7;
                padding: 15px;
                border-radius: 8px;
                margin-top: 20px;
                border-left: 4px solid #f59e0b;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Real Server Monitoring Test</h1>
            <p>This server tracks REAL metrics. Open this page in multiple browsers/devices to see real user counts!</p>
            
            <div id="metrics"></div>
            
            <div style="margin: 30px 0;">
                <button onclick="simulateTransaction()">💳 Simulate Transaction</button>
                <button onclick="refreshMetrics()">🔄 Refresh Metrics</button>
            </div>
            
            <div class="info">
                <strong>📊 How to Test:</strong><br>
                1. Open this page in multiple browsers (Chrome, Safari, Firefox)<br>
                2. Open on your phone<br>
                3. Share with 2-3 friends to test<br>
                4. Click "Simulate Transaction" to add transactions<br>
                5. Watch metrics update in real-time<br>
                6. Check your monitoring system for REAL data!
            </div>
        </div>
        
        <script>
            async function refreshMetrics() {
                const response = await fetch('/api/metrics');
                const data = await response.json();
                
                document.getElementById('metrics').innerHTML = `
                    <div class="metric">
                        <h3>👥 Connected Users</h3>
                        <p>${data.connected_users}</p>
                        <small>Users active in last 5 minutes</small>
                    </div>
                    <div class="metric">
                        <h3>📈 Transactions/Minute</h3>
                        <p>${data.transactions_per_minute}</p>
                        <small>Transactions in last 60 seconds</small>
                    </div>
                    <div class="metric">
                        <h3>💰 Total Transactions</h3>
                        <p>${data.total_transactions}</p>
                        <small>All time</small>
                    </div>
                    <div class="metric">
                        <h3>⏱️ Uptime</h3>
                        <p>${Math.floor(data.uptime_seconds / 60)} minutes</p>
                        <small>${data.uptime_seconds} seconds</small>
                    </div>
                `;
            }
            
            async function simulateTransaction() {
                await fetch('/api/transaction', { method: 'POST' });
                await refreshMetrics();
                alert('Transaction recorded! 💰');
            }
            
            // Auto-refresh every 10 seconds
            refreshMetrics();
            setInterval(refreshMetrics, 10000);
        </script>
    </body>
    </html>
    '''

@app.route('/api/metrics')
def api_metrics():
    """Get current metrics - REAL"""
    track_user_visit()
    
    return jsonify({
        'connected_users': get_connected_users(),
        'transactions_per_minute': get_transactions_per_minute(),
        'total_transactions': get_total_transactions(),
        'uptime_seconds': int(time.time() - start_time)
    })

@app.route('/api/transaction', methods=['POST'])
def api_transaction():
    """Simulate a transaction - REAL tracking"""
    track_user_visit()
    track_transaction()
    
    return jsonify({'success': True})

@app.route('/ping', methods=['GET'])
def ping():
    """Health check endpoint for monitoring - ALL REAL METRICS"""
    try:
        # Track this request as a visit
        track_user_visit()
        
        # Get REAL metrics
        users = get_connected_users()
        tpm = get_transactions_per_minute()
        total = get_total_transactions()
        uptime = int(time.time() - start_time)
        
        # Check if services are healthy
        is_healthy = True
        error_msg = None
        
        if USE_REDIS:
            try:
                r.ping()
            except:
                is_healthy = False
                error_msg = "Redis connection lost"
        
        response = {
            "status": "healthy" if is_healthy else "critical",
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                "transactions_per_minute": tpm,
                "connected_users": users,
                "total_transactions": total,
                "uptime_seconds": uptime,
                "response_time_ms": 50  # Real would be tracked in middleware
            },
            "server": "render-test-server",
            "version": "1.0.0",
            "storage": "redis" if USE_REDIS else "memory"
        }
        
        if not is_healthy:
            response["error"] = error_msg
            response["error_code"] = "REDIS_CONNECTION_ERROR"
            return jsonify(response), 503
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({
            "status": "critical",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "error_code": "INTERNAL_ERROR"
        }), 503

@app.route('/health')
def health():
    """Simple health check"""
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"🚀 Real Server starting on port {port}")
    print(f"📊 Storage: {'Redis' if USE_REDIS else 'In-Memory'}")
    print(f"🔗 Visit the homepage to see real metrics!")
    app.run(host='0.0.0.0', port=port, debug=False)
