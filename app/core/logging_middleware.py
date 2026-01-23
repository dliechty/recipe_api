import logging
import json
import time
import random
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Configure a specific logger for structured events
# We don't propagate to the root logger to avoid double logging if root captures everything
structured_logger = logging.getLogger("api.structured_log")
structured_logger.propagate = False

# Ensure it has a handler if not already configured (though ideally configured in logging.ini)
# For safety, we check handlers. If none, add a StreamHandler.
if not structured_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(message)s"
    )  # Raw message only (which will be JSON)
    handler.setFormatter(formatter)
    structured_logger.addHandler(handler)
    structured_logger.setLevel(logging.INFO)


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to implement wide-event structured logging with tail sampling.

    Rules:
    1. Always log errors (Status >= 500)
    2. Always log slow requests (> 500ms)
    3. Normally we would sample requests (say, 5%) but for testing we log all requests
    """

    SLOW_THRESHOLD_MS = 500
    SAMPLE_RATE = 0.05

    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()

        response = None
        error_details = None
        status_code = 500  # Default to 500 if exception occurs

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            error_details = str(e)
            raise e  # Re-raise exception after capturing it
        finally:
            duration = time.perf_counter() - start_time
            duration_ms = duration * 1000

            should_log = False

            # Rule 1: Always log errors
            if status_code >= 500:
                should_log = True

            # Rule 2: Always keep slow requests
            elif duration_ms > self.SLOW_THRESHOLD_MS:
                should_log = True

            # Rule 3: Randomly sample 5%
            elif random.random() < self.SAMPLE_RATE:
                should_log = True

            if should_log:
                # Extract user info if available
                user_id = None
                user_email = None
                user_name = None

                if hasattr(request.state, "user"):
                    user = request.state.user
                    user_id = str(user.id)
                    user_email = user.email
                    if user.first_name or user.last_name:
                        user_name = (
                            f"{user.first_name or ''} {user.last_name or ''}".strip()
                        )

                log_payload = {
                    "timestamp": time.time(),
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 2),
                    "client_ip": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                    "query_params": dict(request.query_params),
                    "error": error_details,
                    "user_id": user_id,
                    "user_email": user_email,
                    "user_name": user_name,
                }

                # Dump to JSON and log
                structured_logger.info(json.dumps(log_payload))

        return response
