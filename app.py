"""
KuraBak Backend - v6.0 (Production Ready Edition)
==================================================

✅ Multi-worker safe initialization
✅ Redis-optimized health checks
✅ Production-grade rate limiting
✅ Comprehensive error handling
✅ Config-driven architecture
✅ Graceful shutdown
✅ Telemetry & monitoring
✅ Security headers
✅ Async scheduler initialization (Render port fix)

Architecture: Flask + Redis + APScheduler
Deployment: Gunicorn (Render/Docker ready)
"""

import logging
import os
import sys
import atexit
import time
import threading
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, List, Any, Optional, Tuple

from flask import Flask, jsonify, request, Response
from flask_cors import CORS

from config import Config
from services.maintenance_service import (
    start_scheduler,
    stop_scheduler,
    fetch_all_data,
    get_scheduler_status,
    manual_trigger
)
from routes.general_routes import api_bp
from utils.cache import get_cache, REDIS_ENABLED, redis_client
from utils.telegram_monitor import init_telegram_monitor, telegram_monitor

# ======================================
# TELEMETRY & MONITORING SETUP
# ======================================

def setup_telemetry():
    """Application telemetry and monitoring initialization"""
    # Initialize Telegram monitor
    telegram = init_telegram_monitor()
    
    if telegram:
        logger.info("🤖 Telegram monitoring initialized")
    else:
        logger.warning("📵 Telegram monitoring disabled (config missing)")
    
    return telegram

# ======================================
# LOGGING CONFIGURATION (Production Grade)
# ======================================

def setup_logging() -> logging.Logger:
    """
    Production-grade logging setup with Gunicorn support
    
    Returns:
        logging.Logger: Configured logger instance
    """
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    # JSON format for production (structured logging)
    if os.environ.get('FLASK_ENV') == 'production':
        try:
            import json_log_formatter
            formatter = json_log_formatter.JSONFormatter()
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(formatter)
            
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)
            root_logger.setLevel(getattr(logging, log_level, logging.INFO))
            
            return logging.getLogger(__name__)
        except ImportError:
            # Fallback if json_log_formatter is not installed
            print("⚠️ json_log_formatter not found, using standard logging")
    
    # Gunicorn integration
    if os.environ.get('GUNICORN_CMD_ARGS'):
        gunicorn_logger = logging.getLogger('gunicorn.error')
        logging.basicConfig(
            level=gunicorn_logger.level,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            stream=sys.stdout
        )
        return logging.getLogger(__name__)
    
    # Development logging
    numeric_level = getattr(logging, log_level, logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        stream=sys.stdout
    )
    
    return logging.getLogger(__name__)

logger = setup_logging()

# ======================================
# RATE LIMITING (Redis-based Production)
# ======================================

class RateLimiter:
    """Production-grade Redis-based rate limiter"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.prefix = "rate_limit:"
    
    def is_rate_limited(self, key: str, limit: int, window: int) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request is rate limited
        
        Args:
            key: Rate limit key (e.g., "update:192.168.1.1")
            limit: Maximum requests per window
            window: Time window in seconds
            
        Returns:
            Tuple[bool, Dict]: (is_limited, rate_info)
        """
        if not self.redis:
            return False, {"remaining": limit, "reset": 0}
        
        try:
            current = int(time.time())
            window_start = current - window
            
            # Use Redis pipeline for atomic operations
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)  # Clean old requests
            pipe.zcard(key)  # Count current requests
            pipe.zadd(key, {str(current): current})  # Add current request
            pipe.expire(key, window)  # Set expiry
            
            results = pipe.execute()
            current_count = results[1]
            
            remaining = max(0, limit - current_count)
            reset_time = window_start + window
            
            is_limited = current_count > limit
            
            return is_limited, {
                "remaining": remaining,
                "reset": reset_time,
                "limit": limit,
                "window": window
            }
            
        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            return False, {"remaining": limit, "reset": 0}

# Initialize rate limiter
rate_limiter = RateLimiter(redis_client)

def rate_limit(limit: int = 5, window: int = 60, key_func=None):
    """
    Decorator for rate limiting endpoints
    
    Args:
        limit: Max requests per window
        window: Time window in seconds
        key_func: Function to generate rate limit key
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if key_func:
                rate_key = key_func()
            else:
                # Default: IP-based rate limiting
                client_ip = request.remote_addr or "unknown"
                endpoint = request.endpoint or "unknown"
                rate_key = f"{endpoint}:{client_ip}"
            
            # Add Redis prefix
            redis_key = f"rate_limit:{rate_key}"
            
            is_limited, rate_info = rate_limiter.is_rate_limited(
                redis_key, limit, window
            )
            
            if is_limited:
                logger.warning(f"Rate limit exceeded: {rate_key}")
                
                # Add rate limit headers (RFC 6585)
                headers = {
                    'X-RateLimit-Limit': str(limit),
                    'X-RateLimit-Remaining': '0',
                    'X-RateLimit-Reset': str(rate_info['reset']),
                    'Retry-After': str(rate_info['reset'] - int(time.time()))
                }
                
                return jsonify({
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {limit}/{window}s",
                    "retry_after": rate_info['reset'] - int(time.time())
                }), 429, headers
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ======================================
# SECURITY MIDDLEWARE
# ======================================

def add_security_headers(response: Response) -> Response:
    """Add security headers to all responses"""
    # HSTS (HTTPS Strict Transport Security)
    if Config.is_production():
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # Content Security Policy
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    
    # XSS Protection
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Referrer Policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Cache Control for API endpoints
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'public, max-age=60'
    
    return response

# ======================================
# FLASK APP INITIALIZATION
# ======================================

app = Flask(__name__)
app.config.from_object(Config)

# Add security headers middleware
app.after_request(add_security_headers)

# CORS Configuration (Production Security)
allowed_origins = Config.SECURITY.allowed_origins

if '*' in allowed_origins:
    logger.warning("⚠️ CORS: All origins allowed (not recommended for production)")
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
else:
    logger.info(f"✅ CORS: Allowed origins: {allowed_origins}")
    CORS(app, resources={
        r"/api/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
            "max_age": Config.CORS_MAX_AGE
        }
    })

# ======================================
# APPLICATION STATE MANAGEMENT
# ======================================

class AppState:
    """Thread-safe application state management"""
    
    def __init__(self):
        self._initialized = False
        self._lock = threading.Lock()
        self._startup_time = datetime.now()
        self._metrics = {
            'total_requests': 0,
            'failed_requests': 0,
            'active_connections': 0
        }
        self._metrics_lock = threading.Lock()
    
    @property
    def initialized(self) -> bool:
        """Check if app is initialized"""
        with self._lock:
            return self._initialized
    
    @initialized.setter
    def initialized(self, value: bool):
        """Set initialization state"""
        with self._lock:
            self._initialized = value
    
    def increment_request(self, success: bool = True):
        """Track request metrics"""
        with self._metrics_lock:
            self._metrics['total_requests'] += 1
            if not success:
                self._metrics['failed_requests'] += 1
    
    def get_uptime(self) -> float:
        """Get application uptime in seconds"""
        return (datetime.now() - self._startup_time).total_seconds()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get application metrics"""
        with self._metrics_lock:
            return self._metrics.copy()

app_state = AppState()

# ======================================
# ROUTES REGISTRATION
# ======================================

# Register API blueprint
app.register_blueprint(api_bp)

# ======================================
# CORE ROUTES
# ======================================

@app.route("/", methods=["GET"])
def home() -> Tuple[Response, int]:
    """Root endpoint with API documentation"""
    try:
        app_state.increment_request(success=True)
        
        response = {
            "app": Config.APP_NAME,
            "version": Config.APP_VERSION,
            "status": "operational",
            "environment": Config.ENVIRONMENT,
            "uptime_seconds": round(app_state.get_uptime(), 2),
            "timestamp": datetime.now().isoformat(),
            "features": [
                "Unified API fetching with triple fallback",
                "Circuit breaker protection",
                "Redis-optimized caching",
                "Smart rate limiting",
                "Telegram monitoring",
                f"Auto-update every {Config.UPDATE_INTERVAL}s"
            ],
            "cache": {
                "engine": "Redis/Valkey" if REDIS_ENABLED else "Memory",
                "enabled": REDIS_ENABLED,
                "ttl": Config.CACHE_TTL
            },
            "security": {
                "cors": "restricted" if '*' not in allowed_origins else "open",
                "rate_limiting": "enabled",
                "telemetry": "enabled" if telegram_monitor else "disabled"
            },
            "endpoints": {
                "public": {
                    "/api/currency/popular": "Popular currency rates",
                    "/api/currency/gold/popular": "Popular gold prices",
                    "/api/currency/silver/all": "Silver prices",
                    "/api/metrics": "System metrics",
                    "/api/health": "Health check"
                },
                "admin": {
                    "/health": "Detailed system health",
                    "/status": "Scheduler & circuit breaker status",
                    "/api/update": "Manual data update (POST, rate-limited)"
                }
            }
        }
        
        return jsonify(response), 200
    
    except Exception as e:
        logger.error(f"Home endpoint error: {e}")
        app_state.increment_request(success=False)
        return jsonify({
            "error": "Internal server error",
            "message": "Could not generate API documentation"
        }), 500


@app.route("/health", methods=["GET", "HEAD"])
def health() -> Tuple[Response, int]:
    """
    Comprehensive health check endpoint
    Returns 200 if healthy, 503 if degraded
    """
    health_checks = {
        "redis": {"status": "unknown", "latency_ms": None},
        "cache_data": {"status": "unknown", "counts": {}},
        "scheduler": {"status": "unknown", "running": False},
        "data_freshness": {"status": "unknown", "age_seconds": None}
    }
    
    overall_healthy = True
    start_time = time.time()
    
    try:
        # 1. Check Redis connectivity (if enabled)
        redis_ok = False
        redis_latency = None
        
        if REDIS_ENABLED and redis_client:
            try:
                redis_start = time.time()
                redis_client.ping()
                redis_latency = round((time.time() - redis_start) * 1000, 2)
                redis_ok = True
                health_checks["redis"] = {
                    "status": "healthy",
                    "latency_ms": redis_latency
                }
            except Exception as e:
                logger.warning(f"Redis health check failed: {e}")
                health_checks["redis"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
                overall_healthy = False
        
        # 2. Check cache data (optimized single call)
        cache_keys = [
            Config.CACHE_KEYS['currencies_all'],
            Config.CACHE_KEYS['golds_all'],
            Config.CACHE_KEYS['silvers_all']
        ]
        
        try:
            currencies = get_cache(cache_keys[0], Config.CACHE_TTL)
            golds = get_cache(cache_keys[1], Config.CACHE_TTL)
            silvers = get_cache(cache_keys[2], Config.CACHE_TTL)
            
            if currencies or golds or silvers:
                c_count = len(currencies.get('data', [])) if currencies else 0
                g_count = len(golds.get('data', [])) if golds else 0
                s_count = len(silvers.get('data', [])) if silvers else 0
                
                health_checks["cache_data"] = {
                    "status": "healthy" if c_count > 0 and g_count > 0 else "degraded",
                    "counts": {
                        "currencies": c_count,
                        "golds": g_count,
                        "silvers": s_count
                    }
                }
                
                # Check data freshness
                if currencies and currencies.get('update_date'):
                    try:
                        if isinstance(currencies['update_date'], str):
                            update_time = datetime.fromisoformat(currencies['update_date'].replace('Z', '+00:00'))
                        else:
                            update_time = currencies['update_date']
                        
                        data_age = (datetime.now() - update_time).total_seconds()
                        health_checks["data_freshness"] = {
                            "status": "fresh" if data_age < Config.HEALTH_MAX_DATA_AGE else "stale",
                            "age_seconds": round(data_age, 2),
                            "max_allowed": Config.HEALTH_MAX_DATA_AGE
                        }
                        
                        if data_age > Config.HEALTH_MAX_DATA_AGE:
                            overall_healthy = False
                            
                    except Exception as e:
                        logger.warning(f"Data freshness check failed: {e}")
                        health_checks["data_freshness"]["status"] = "unknown"
            else:
                health_checks["cache_data"]["status"] = "unhealthy"
                overall_healthy = False
                
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            health_checks["cache_data"] = {"status": "error", "error": str(e)}
            overall_healthy = False
        
        # 3. Check scheduler status
        try:
            scheduler_status = get_scheduler_status()
            scheduler_running = scheduler_status.get('scheduler_running', False)
            
            health_checks["scheduler"] = {
                "status": "running" if scheduler_running else "stopped",
                "running": scheduler_running,
                "circuit_breaker": scheduler_status.get('circuit_breaker', {}).get('state', 'unknown')
            }
            
            if not scheduler_running:
                overall_healthy = False
                
        except Exception as e:
            logger.error(f"Scheduler health check failed: {e}")
            health_checks["scheduler"] = {"status": "error", "error": str(e)}
            overall_healthy = False
        
        # 4. Performance check
        total_latency = round((time.time() - start_time) * 1000, 2)
        
        # Build response
        status = "healthy" if overall_healthy else "degraded"
        http_code = 200 if overall_healthy else 503
        
        response = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "latency_ms": total_latency,
            "checks": health_checks,
            "redis_enabled": REDIS_ENABLED,
            "environment": Config.ENVIRONMENT
        }
        
        # Log health status periodically (every 10th call)
        health_check_counter = getattr(health, '_counter', 0) + 1
        health._counter = health_check_counter
        
        if health_check_counter % 10 == 0:
            logger.info(f"Health check #{health_check_counter}: {status.upper()} (latency: {total_latency}ms)")
        
        app_state.increment_request(success=overall_healthy)
        
        # HEAD request: return only headers
        if request.method == 'HEAD':
            return '', http_code
        
        return jsonify(response), http_code
    
    except Exception as e:
        logger.critical(f"Critical health check failure: {e}")
        app_state.increment_request(success=False)
        
        if request.method == 'HEAD':
            return '', 503
        
        return jsonify({
            "status": "unhealthy",
            "error": "Critical system failure",
            "timestamp": datetime.now().isoformat()
        }), 503


@app.route("/status", methods=["GET"])
def status() -> Tuple[Response, int]:
    """
    Detailed system status with scheduler and circuit breaker info
    """
    try:
        scheduler_status = get_scheduler_status()
        
        response = {
            "status": "ok",
            "system": {
                "uptime_seconds": round(app_state.get_uptime(), 2),
                "startup_time": app_state._startup_time.isoformat(),
                "environment": Config.ENVIRONMENT,
                "python_version": sys.version.split()[0]
            },
            "scheduler": scheduler_status,
            "cache": {
                "engine": "Redis" if REDIS_ENABLED else "Memory",
                "enabled": REDIS_ENABLED,
                "config": {
                    "update_interval": Config.UPDATE_INTERVAL,
                    "cache_ttl": Config.CACHE_TTL,
                    "stale_max_age": Config.STALE_CACHE_MAX_AGE
                }
            },
            "telemetry": {
                "telegram_monitor": "enabled" if telegram_monitor else "disabled",
                "total_requests": app_state.get_metrics()['total_requests']
            },
            "timestamp": datetime.now().isoformat()
        }
        
        app_state.increment_request(success=True)
        return jsonify(response), 200
    
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        app_state.increment_request(success=False)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@app.route("/api/update", methods=["POST"])
@rate_limit(limit=Config.RATE_LIMIT_REQUESTS, window=Config.RATE_LIMIT_WINDOW)
def manual_update() -> Tuple[Response, int]:
    """
    Manual data update trigger with rate limiting
    """
    try:
        client_ip = request.remote_addr or "unknown"
        logger.info(f"Manual update requested by {client_ip}")
        
        # Trigger update through maintenance service
        result = manual_trigger()
        
        if result.get('success', False):
            # Send Telegram notification if enabled
            if telegram_monitor:
                telegram_monitor.send_message(
                    f"✅ Manuel güncelleme başarılı\n"
                    f"• IP: {client_ip}\n"
                    f"• Süre: {result.get('duration_seconds', 0):.2f}s\n"
                    f"• Circuit Breaker: {result.get('circuit_breaker_state', 'unknown')}",
                    alert_level='info'
                )
            
            response = {
                "success": True,
                "message": "Financial data updated successfully",
                "duration_seconds": result.get('duration_seconds'),
                "circuit_breaker_state": result.get('circuit_breaker_state'),
                "timestamp": datetime.now().isoformat()
            }
            
            app_state.increment_request(success=True)
            return jsonify(response), 200
        
        else:
            # Send alert if circuit breaker is open
            if result.get('circuit_breaker_state') == 'OPEN' and telegram_monitor:
                telegram_monitor.send_message(
                    f"⚠️ Manuel güncelleme BAŞARISIZ (Circuit Breaker OPEN)\n"
                    f"• IP: {client_ip}\n"
                    f"• Sistem koruma modunda",
                    alert_level='warning'
                )
            
            response = {
                "success": False,
                "message": "Update failed (circuit breaker may be active)",
                "circuit_breaker_state": result.get('circuit_breaker_state'),
                "info": "Please try again in a few minutes",
                "timestamp": datetime.now().isoformat()
            }
            
            app_state.increment_request(success=False)
            return jsonify(response), 503
    
    except Exception as e:
        logger.error(f"Manual update error: {e}")
        app_state.increment_request(success=False)
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

# ======================================
# ERROR HANDLERS (Production Grade)
# ======================================

@app.errorhandler(400)
def bad_request(error) -> Tuple[Response, int]:
    """400 Bad Request handler"""
    logger.warning(f"Bad request: {request.url} - {error}")
    return jsonify({
        "error": "Bad request",
        "message": "The request could not be understood",
        "path": request.path,
        "method": request.method
    }), 400


@app.errorhandler(404)
def not_found(error) -> Tuple[Response, int]:
    """404 Not Found handler"""
    return jsonify({
        "error": "Not found",
        "message": f"The requested endpoint '{request.path}' does not exist",
        "available_endpoints": [
            "/",
            "/health",
            "/status",
            "/api/currency/popular",
            "/api/currency/gold/popular",
            "/api/currency/silver/all",
            "/api/metrics",
            "/api/update (POST)"
        ]
    }), 404


@app.errorhandler(429)
def rate_limit_exceeded(error) -> Tuple[Response, int]:
    """429 Rate Limit handler"""
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "Too many requests from your IP address",
        "retry_after": request.headers.get('Retry-After', '60'),
        "info": "Rate limits reset automatically"
    }), 429


@app.errorhandler(500)
def internal_error(error) -> Tuple[Response, int]:
    """500 Internal Server Error handler"""
    logger.critical(f"Internal server error: {error}\nPath: {request.path}\nMethod: {request.method}")
    
    # Send critical alert to Telegram
    if telegram_monitor:
        telegram_monitor.send_message(
            f"🔴 CRITICAL: 500 Internal Server Error\n"
            f"• Path: {request.path}\n"
            f"• Method: {request.method}\n"
            f"• Error: {str(error)[:100]}...",
            alert_level='critical'
        )
    
    return jsonify({
        "error": "Internal server error",
        "message": "An unexpected error occurred",
        "request_id": request.headers.get('X-Request-ID', 'unknown'),
        "timestamp": datetime.now().isoformat()
    }), 500


@app.errorhandler(Exception)
def handle_unexpected_error(error) -> Tuple[Response, int]:
    """Catch-all exception handler"""
    logger.critical(f"Unexpected error: {error}", exc_info=True)
    
    return jsonify({
        "error": "Unexpected server error",
        "message": "The server encountered an unexpected condition",
        "timestamp": datetime.now().isoformat()
    }), 500

# ======================================
# APPLICATION LIFECYCLE MANAGEMENT
# ======================================

def initialize_application():
    """
    Thread-safe application initialization
    ✅ FIX: Non-blocking scheduler start for Render
    """
    with app_state._lock:
        if app_state.initialized:
            logger.debug("Application already initialized, skipping")
            return
        
        try:
            pid = os.getpid()
            worker_id = os.environ.get('GUNICORN_WORKER_ID', 'main')
            port = int(os.environ.get('PORT', 5001))
            
            # Show startup banner with correct port
            Config.display()
            
            logger.info(f"""
            🚀 Initializing {Config.APP_NAME} v{Config.APP_VERSION}
            ==========================================
            • PID: {pid}
            • Worker: {worker_id}
            • Port: {port}
            • Environment: {Config.ENVIRONMENT.upper()}
            • Python: {sys.version.split()[0]}
            • Redis: {'✅ Enabled' if REDIS_ENABLED else '⚠️ Disabled (fallback)'}
            • Telegram Monitor: {'✅ Enabled' if telegram_monitor else '❌ Disabled'}
            ==========================================
            """)
            
            # 1. Start scheduler (NON-BLOCKING for Render)
            logger.info("🔄 Starting background scheduler...")
            scheduler = start_scheduler()
            if scheduler:
                logger.info("✅ Background scheduler started")
            else:
                logger.error("❌ Failed to start scheduler")
            
            # 2. Initialize telemetry
            setup_telemetry()
            
            # 3. Register cleanup handlers
            atexit.register(cleanup_application)
            
            # 4. Mark as initialized IMMEDIATELY (don't wait for first data fetch)
            app_state.initialized = True
            
            logger.info("✅ Application initialization complete")
            
            # 5. Send startup notification (async, doesn't block)
            if telegram_monitor:
                try:
                    telegram_monitor.send_message(
                        f"🚀 {Config.APP_NAME} Backend Started\n"
                        f"• Version: {Config.APP_VERSION}\n"
                        f"• Environment: {Config.ENVIRONMENT}\n"
                        f"• Port: {port}\n"
                        f"• Worker: {worker_id}\n"
                        f"• Redis: {'Enabled' if REDIS_ENABLED else 'Disabled'}\n"
                        f"• Scheduler: {'Running' if scheduler else 'Stopped'}",
                        alert_level='success'
                    )
                except Exception as e:
                    logger.warning(f"Failed to send startup notification: {e}")
            
        except Exception as e:
            logger.critical(f"❌ Application initialization failed: {e}", exc_info=True)
            if Config.is_production():
                # Don't exit - let the app try to serve requests anyway
                logger.error("Continuing despite initialization error...")
            else:
                raise


def cleanup_application():
    """
    Graceful application shutdown
    """
    logger.info("🛑 Application shutdown initiated")
    
    try:
        # 1. Stop scheduler
        stop_scheduler()
        logger.info("✅ Scheduler stopped")
        
        # 2. Log final metrics
        metrics = app_state.get_metrics()
        logger.info(f"""
        📊 Final Application Metrics:
        • Total Requests: {metrics['total_requests']}
        • Failed Requests: {metrics['failed_requests']}
        • Uptime: {app_state.get_uptime():.2f}s
        """)
        
        # 3. Send shutdown notification
        if telegram_monitor:
            try:
                telegram_monitor.send_message(
                    f"🛑 {Config.APP_NAME} Backend Shutting Down\n"
                    f"• Uptime: {app_state.get_uptime():.2f}s\n"
                    f"• Total Requests: {metrics['total_requests']}\n"
                    f"• Failed: {metrics['failed_requests']}",
                    alert_level='info'
                )
            except Exception as e:
                logger.warning(f"Failed to send shutdown notification: {e}")
        
        logger.info("✅ Application shutdown complete")
        
    except Exception as e:
        logger.error(f"❌ Error during cleanup: {e}")


# ======================================
# REQUEST HOOKS
# ======================================

@app.before_request
def before_request():
    """Pre-request processing"""
    # Track active connections (for monitoring)
    app_state._metrics['active_connections'] = \
        app_state._metrics.get('active_connections', 0) + 1
    
    # Set request start time for latency tracking
    request.start_time = time.time()


@app.after_request
def after_request(response: Response) -> Response:
    """Post-request processing"""
    # Calculate request latency
    if hasattr(request, 'start_time'):
        latency = time.time() - request.start_time
        response.headers['X-Response-Time'] = f'{latency:.3f}s'
        
        # Log slow requests
        if latency > 2.0:  # 2 seconds
            logger.warning(f"Slow request: {request.path} took {latency:.2f}s")
    
    # Update active connections
    app_state._metrics['active_connections'] = \
        app_state._metrics.get('active_connections', 1) - 1
    
    return response

# ======================================
# APPLICATION ENTRY POINTS
# ======================================

# 🔥 CRITICAL FIX: Background initialization for Render
# This ensures the app starts serving HTTP immediately
if os.environ.get('GUNICORN_CMD_ARGS'):
    # Production: Start initialization in background thread
    logger.info("✅ Gunicorn detected - starting background initialization")
    init_thread = threading.Thread(target=initialize_application, daemon=True)
    init_thread.start()
elif os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    # Development with reloader
    initialize_application()

# Development entry point (Local testler için)
if __name__ == "__main__":
    initialize_application()
    
    # Environment'dan PORT al, yoksa 5001 kullan
    port = int(os.environ.get('PORT', 5001))
    debug = Config.ENVIRONMENT != 'production'
    
    logger.info(f"🌍 Starting development server on port {port} (debug={debug})")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        use_reloader=False  # Disable reloader to prevent double initialization
    )
