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

# Middleware to track response times
@app.before_request
def start_timer():
    """Start timing the request"""
    from flask import g
    g.start_time = time.time()

@app.after_request
def track_response_time(response):
    """Track response time after each request"""
    from flask import g
    if hasattr(g, 'start_time'):
        elapsed_ms = (time.time() - g.start_time) * 1000
        response_times.append(elapsed_ms)
        # Keep only last 100 response times
        if len(response_times) > 100:
            response_times.pop(0)
    return response

# Track server start time
start_time = time.time()

# Configuration
USER_TIMEOUT_SECONDS = 30  # Users inactive for 30 seconds are removed

# Testing variables - for simulating errors
force_critical = False
critical_error_message = None

# In-memory storage (for free tier without Redis)
# In production, use Redis for persistence
visit_log = []  # List of {timestamp, user_id}
page_views = defaultdict(int)
transaction_log = []  # List of transaction timestamps
response_times = []  # List of response times for tracking

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
        # Store in Redis with 30 second expiry
        r.hset(f'user:{user_id}', 'last_seen', timestamp)
        r.expire(f'user:{user_id}', USER_TIMEOUT_SECONDS)
    else:
        # Store in memory - update existing user or add new
        # Remove old entries for this user
        visit_log[:] = [v for v in visit_log if v['user_id'] != user_id]
        # Add new entry
        visit_log.append({'timestamp': timestamp, 'user_id': user_id})
        # Clean old visits (older than timeout)
        cutoff = time.time() - USER_TIMEOUT_SECONDS
        visit_log[:] = [v for v in visit_log if v['timestamp'] > cutoff]

def get_connected_users():
    """Get count of users active in last 30 seconds - REAL"""
    if USE_REDIS:
        count = 0
        for key in r.scan_iter('user:*'):
            count += 1
        return count
    else:
        # Count unique users in last 30 seconds
        cutoff = time.time() - USER_TIMEOUT_SECONDS
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

def get_average_response_time():
    """Get average response time from tracked responses - REAL"""
    if not response_times:
        return 0
    return round(sum(response_times) / len(response_times), 2)

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
                6. Check your monitoring system for REAL data!<br>
                <br>
                <strong>🔗 Quick Links:</strong><br>
                📊 <a href="/status" style="color: #2563eb; text-decoration: underline;">Service Status Page</a> - Professional status dashboard<br>
                🧪 <a href="/test-controls" style="color: #2563eb; text-decoration: underline;">Error Testing Controls</a> - Test Slack alerts
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
                        <small>Users active in last 30 seconds</small>
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
                        <h3>⚡ Response Time</h3>
                        <p>${data.response_time_ms || 0} ms</p>
                        <small>Average of last 100 requests</small>
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
        'uptime_seconds': int(time.time() - start_time),
        'response_time_ms': get_average_response_time()
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
        response_time = get_average_response_time()
        
        # Check if services are healthy
        is_healthy = True
        error_msg = None
        error_code = None
        
        # Check for forced critical state (for testing)
        if force_critical:
            is_healthy = False
            error_msg = critical_error_message
            error_code = "SIMULATED_ERROR"
        elif USE_REDIS:
            try:
                r.ping()
            except:
                is_healthy = False
                error_msg = "Redis connection lost"
                error_code = "REDIS_CONNECTION_ERROR"
        
        response = {
            "status": "healthy" if is_healthy else "critical",
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                "transactions_per_minute": tpm,
                "connected_users": users,
                "total_transactions": total,
                "uptime_seconds": uptime,
                "response_time_ms": response_time
            },
            "server": "render-test-server",
            "version": "1.0.0",
            "storage": "redis" if USE_REDIS else "memory"
        }
        
        if not is_healthy:
            response["error"] = error_msg
            response["error_code"] = error_code
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

# ==============================================================================
# TESTING ENDPOINTS - Simulate errors to test Slack alerts
# ==============================================================================

@app.route('/simulate-error', methods=['POST'])
def simulate_error():
    """
    Force server into critical state to test alerts
    POST to this endpoint to trigger critical error
    """
    global force_critical, critical_error_message
    
    error_type = request.json.get('error_type', 'database') if request.json else 'database'
    
    error_messages = {
        'database': 'Database connection pool exhausted',
        'memory': 'Memory usage critical - 95% used',
        'disk': 'Disk space critical - 98% full',
        'api': 'External API timeout - payment gateway unreachable',
        'cpu': 'CPU usage critical - 99% sustained load'
    }
    
    force_critical = True
    critical_error_message = error_messages.get(error_type, 'Unknown critical error')
    
    return jsonify({
        'message': 'Server forced into CRITICAL state',
        'error': critical_error_message,
        'note': 'Check /ping endpoint - it will return critical status',
        'restore': 'POST to /force-healthy to restore'
    }), 200

@app.route('/force-healthy', methods=['POST'])
def force_healthy():
    """Restore server to healthy state"""
    global force_critical, critical_error_message
    
    force_critical = False
    critical_error_message = None
    
    return jsonify({
        'message': 'Server restored to HEALTHY state',
        'note': 'Check /ping endpoint - it will return healthy status'
    }), 200

@app.route('/simulate-crash', methods=['POST'])
def simulate_crash():
    """
    Simulate a server crash (raises exception)
    Use this to test server down alerts
    """
    raise Exception("Simulated server crash - testing error handling")

@app.route('/api/status')
def api_status():
    """
    JSON API for status (for external monitoring)
    """
    services = []
    overall_status = "operational"
    
    # Check all services
    try:
        services.append({"name": "Web Server", "status": "operational"})
    except:
        services.append({"name": "Web Server", "status": "down"})
        overall_status = "down"
    
    try:
        get_connected_users()
        services.append({"name": "API Services", "status": "operational"})
    except:
        services.append({"name": "API Services", "status": "degraded"})
        overall_status = "degraded"
    
    if USE_REDIS:
        try:
            r.ping()
            services.append({"name": "Redis Cache", "status": "operational"})
        except:
            services.append({"name": "Redis Cache", "status": "down"})
            overall_status = "degraded"
    
    if force_critical:
        services.append({"name": "Health Check", "status": "critical", "error": critical_error_message})
        overall_status = "critical"
    else:
        services.append({"name": "Health Check", "status": "operational"})
    
    return jsonify({
        "overall_status": overall_status,
        "services": services,
        "metrics": {
            "connected_users": get_connected_users(),
            "transactions_per_minute": get_transactions_per_minute(),
            "response_time_ms": get_average_response_time(),
            "uptime_seconds": int(time.time() - start_time)
        },
        "timestamp": datetime.now().isoformat()
    })

@app.route('/status')
def status_page():
    """
    Public status page showing all services health
    Similar to status.mongodb.com
    """
    # Check all services
    services_status = []
    overall_status = "operational"
    
    # Check main server
    try:
        services_status.append({
            "name": "Web Server",
            "status": "operational",
            "description": "Main application server"
        })
    except:
        services_status.append({
            "name": "Web Server",
            "status": "down",
            "description": "Main application server"
        })
        overall_status = "down"
    
    # Check API endpoints
    try:
        users = get_connected_users()
        services_status.append({
            "name": "API Services",
            "status": "operational",
            "description": "REST API endpoints"
        })
    except:
        services_status.append({
            "name": "API Services",
            "status": "degraded",
            "description": "REST API endpoints"
        })
        overall_status = "degraded"
    
    # Check database/storage
    if USE_REDIS:
        try:
            r.ping()
            services_status.append({
                "name": "Redis Cache",
                "status": "operational",
                "description": "Data caching layer"
            })
        except:
            services_status.append({
                "name": "Redis Cache",
                "status": "down",
                "description": "Data caching layer"
            })
            overall_status = "degraded"
    else:
        services_status.append({
            "name": "In-Memory Storage",
            "status": "operational",
            "description": "Temporary data storage"
        })
    
    # Check monitoring endpoint
    try:
        tpm = get_transactions_per_minute()
        services_status.append({
            "name": "Monitoring & Metrics",
            "status": "operational",
            "description": "Real-time metrics tracking"
        })
    except:
        services_status.append({
            "name": "Monitoring & Metrics",
            "status": "degraded",
            "description": "Real-time metrics tracking"
        })
    
    # Check if forced critical
    if force_critical:
        services_status.append({
            "name": "Health Check System",
            "status": "critical",
            "description": f"Critical error: {critical_error_message}"
        })
        overall_status = "critical"
    else:
        services_status.append({
            "name": "Health Check System",
            "status": "operational",
            "description": "Service health monitoring"
        })
    
    # Add uptime info
    uptime_hours = int((time.time() - start_time) / 3600)
    uptime_minutes = int((time.time() - start_time) / 60) % 60
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Service Status</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            
            .container {{
                max-width: 900px;
                margin: 0 auto;
            }}
            
            .header {{
                background: white;
                border-radius: 12px 12px 0 0;
                padding: 40px;
                text-align: center;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            
            .header h1 {{
                color: #1e293b;
                font-size: 32px;
                margin-bottom: 10px;
            }}
            
            .header p {{
                color: #64748b;
                font-size: 16px;
            }}
            
            .overall-status {{
                background: {"#10b981" if overall_status == "operational" else "#ef4444" if overall_status == "down" else "#f59e0b"};
                color: white;
                padding: 30px;
                text-align: center;
                font-size: 24px;
                font-weight: 600;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            
            .services {{
                background: white;
                border-radius: 0 0 12px 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                overflow: hidden;
            }}
            
            .service-item {{
                padding: 24px 40px;
                border-bottom: 1px solid #e2e8f0;
                display: flex;
                justify-content: space-between;
                align-items: center;
                transition: background 0.2s;
            }}
            
            .service-item:hover {{
                background: #f8fafc;
            }}
            
            .service-item:last-child {{
                border-bottom: none;
            }}
            
            .service-info {{
                flex: 1;
            }}
            
            .service-name {{
                font-size: 18px;
                font-weight: 600;
                color: #1e293b;
                margin-bottom: 5px;
            }}
            
            .service-description {{
                font-size: 14px;
                color: #64748b;
            }}
            
            .service-status {{
                padding: 8px 20px;
                border-radius: 20px;
                font-size: 14px;
                font-weight: 600;
                text-transform: capitalize;
            }}
            
            .status-operational {{
                background: #d1fae5;
                color: #065f46;
            }}
            
            .status-degraded {{
                background: #fef3c7;
                color: #92400e;
            }}
            
            .status-down {{
                background: #fee2e2;
                color: #991b1b;
            }}
            
            .status-critical {{
                background: #fee2e2;
                color: #991b1b;
            }}
            
            .footer {{
                background: white;
                margin-top: 30px;
                padding: 30px 40px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            
            .footer-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
            }}
            
            .footer-item {{
                text-align: center;
            }}
            
            .footer-label {{
                color: #64748b;
                font-size: 14px;
                margin-bottom: 8px;
            }}
            
            .footer-value {{
                color: #1e293b;
                font-size: 24px;
                font-weight: 600;
            }}
            
            .refresh-note {{
                text-align: center;
                color: white;
                margin-top: 20px;
                font-size: 14px;
                opacity: 0.9;
            }}
            
            @media (max-width: 768px) {{
                .header {{
                    padding: 30px 20px;
                }}
                
                .header h1 {{
                    font-size: 24px;
                }}
                
                .overall-status {{
                    padding: 20px;
                    font-size: 20px;
                }}
                
                .service-item {{
                    padding: 20px;
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 15px;
                }}
                
                .footer {{
                    padding: 20px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 Service Status Dashboard</h1>
                <p>Real-time monitoring of all services and components</p>
            </div>
            
            <div class="overall-status">
                {"✅ All Systems Operational" if overall_status == "operational" else "⚠️ Some Systems Degraded" if overall_status == "degraded" else "🚨 System Issues Detected"}
            </div>
            
            <div class="services">
                {"".join([f'''
                <div class="service-item">
                    <div class="service-info">
                        <div class="service-name">{service["name"]}</div>
                        <div class="service-description">{service["description"]}</div>
                    </div>
                    <div class="service-status status-{service["status"]}">
                        {service["status"].title()}
                    </div>
                </div>
                ''' for service in services_status])}
            </div>
            
            <div class="footer">
                <div class="footer-grid">
                    <div class="footer-item">
                        <div class="footer-label">Connected Users</div>
                        <div class="footer-value">{get_connected_users()}</div>
                    </div>
                    <div class="footer-item">
                        <div class="footer-label">Transactions/Min</div>
                        <div class="footer-value">{get_transactions_per_minute()}</div>
                    </div>
                    <div class="footer-item">
                        <div class="footer-label">Response Time</div>
                        <div class="footer-value">{get_average_response_time()} ms</div>
                    </div>
                    <div class="footer-item">
                        <div class="footer-label">Uptime</div>
                        <div class="footer-value">{uptime_hours}h {uptime_minutes}m</div>
                    </div>
                </div>
            </div>
            
            <div class="refresh-note">
                Page auto-refreshes every 30 seconds
            </div>
        </div>
        
        <script>
            // Auto-refresh every 30 seconds
            setTimeout(() => {{
                location.reload();
            }}, 30000);
        </script>
    </body>
    </html>
    '''

@app.route('/test-controls')
def test_controls():
    """
    Web interface to test error scenarios
    """
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Error Testing Controls</title>
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
            h1 { color: #dc2626; }
            h2 { color: #2563eb; margin-top: 30px; }
            .button-group {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin: 20px 0;
            }
            button {
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 16px;
                font-weight: 500;
            }
            .error-btn {
                background: #dc2626;
                color: white;
            }
            .error-btn:hover {
                background: #b91c1c;
            }
            .success-btn {
                background: #16a34a;
                color: white;
            }
            .success-btn:hover {
                background: #15803d;
            }
            .warning {
                background: #fef3c7;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
                border-left: 4px solid #f59e0b;
            }
            .info {
                background: #dbeafe;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
                border-left: 4px solid #2563eb;
            }
            #status {
                margin-top: 20px;
                padding: 15px;
                border-radius: 8px;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🧪 Error Testing Controls</h1>
            <p>Use these controls to simulate server errors and test your Slack alerts!</p>
            
            <div class="warning">
                <strong>⚠️ Note:</strong> These controls will trigger REAL alerts in Slack.
                Make sure your monitoring script is running!
            </div>
            
            <h2>🔴 Simulate Critical Errors</h2>
            <p>These will make /ping return "critical" status with error messages:</p>
            
            <div class="button-group">
                <button class="error-btn" onclick="simulateError('database')">
                    🗄️ Database Error
                </button>
                <button class="error-btn" onclick="simulateError('memory')">
                    🧠 Memory Critical
                </button>
                <button class="error-btn" onclick="simulateError('disk')">
                    💾 Disk Full
                </button>
                <button class="error-btn" onclick="simulateError('api')">
                    🔌 API Timeout
                </button>
                <button class="error-btn" onclick="simulateError('cpu')">
                    ⚡ CPU Overload
                </button>
            </div>
            
            <h2>✅ Restore to Healthy</h2>
            <p>Click this to restore server to healthy state:</p>
            
            <button class="success-btn" onclick="forceHealthy()">
                ✅ Restore Healthy Status
            </button>
            
            <div class="info">
                <strong>📊 How to test:</strong><br>
                1. Make sure your monitor.py is running<br>
                2. Click any error button above<br>
                3. Wait 30 seconds (next monitoring check)<br>
                4. Check Slack for critical alert with error details<br>
                5. Click "Restore Healthy Status"<br>
                6. Check Slack for recovery alert
            </div>
            
            <h2>📍 Check Current Status</h2>
            <button class="success-btn" onclick="checkStatus()">
                🔍 Check /ping Status
            </button>
            
            <div id="status"></div>
        </div>
        
        <script>
            async function simulateError(type) {
                try {
                    const response = await fetch('/simulate-error', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({error_type: type})
                    });
                    const data = await response.json();
                    
                    document.getElementById('status').innerHTML = `
                        <div style="background: #fee2e2; color: #991b1b; padding: 15px; border-radius: 8px;">
                            <strong>🚨 CRITICAL ERROR ACTIVATED</strong><br>
                            Error: ${data.error}<br>
                            <small>Your monitoring script should detect this in ~30 seconds</small>
                        </div>
                    `;
                    
                    alert('✅ Critical error activated!\\n\\nError: ' + data.error + '\\n\\nCheck Slack in 30 seconds for alert!');
                } catch (error) {
                    alert('❌ Failed: ' + error);
                }
            }
            
            async function forceHealthy() {
                try {
                    const response = await fetch('/force-healthy', {
                        method: 'POST'
                    });
                    const data = await response.json();
                    
                    document.getElementById('status').innerHTML = `
                        <div style="background: #dcfce7; color: #166534; padding: 15px; border-radius: 8px;">
                            <strong>✅ SERVER RESTORED TO HEALTHY</strong><br>
                            <small>Your monitoring script should detect recovery in ~30 seconds</small>
                        </div>
                    `;
                    
                    alert('✅ Server restored to healthy!\\n\\nCheck Slack in 30 seconds for recovery alert!');
                } catch (error) {
                    alert('❌ Failed: ' + error);
                }
            }
            
            async function checkStatus() {
                try {
                    const response = await fetch('/ping');
                    const data = await response.json();
                    
                    const isHealthy = data.status === 'healthy';
                    const bgColor = isHealthy ? '#dcfce7' : '#fee2e2';
                    const textColor = isHealthy ? '#166534' : '#991b1b';
                    
                    document.getElementById('status').innerHTML = `
                        <div style="background: ${bgColor}; color: ${textColor}; padding: 15px; border-radius: 8px;">
                            <strong>Status: ${data.status.toUpperCase()}</strong><br>
                            ${data.error ? 'Error: ' + data.error + '<br>' : ''}
                            Connected Users: ${data.metrics.connected_users}<br>
                            Transactions/Min: ${data.metrics.transactions_per_minute}<br>
                            Response Time: ${data.metrics.response_time_ms}ms<br>
                            Uptime: ${Math.floor(data.metrics.uptime_seconds / 60)} minutes
                        </div>
                    `;
                } catch (error) {
                    alert('❌ Failed to check status: ' + error);
                }
            }
        </script>
    </body>
    </html>
    '''

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"🚀 Real Server starting on port {port}")
    print(f"📊 Storage: {'Redis' if USE_REDIS else 'In-Memory'}")
    print(f"🔗 Visit the homepage to see real metrics!")
    app.run(host='0.0.0.0', port=port, debug=False)
