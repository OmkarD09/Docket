"""PayPal integration package for Docket."""

from docket.paypal.client import (
    PayPalSandboxClient,
    PayPalDisputeError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    RateLimitError,
    PayPalServerError,
    NetworkError,
    TimeoutError,
    MalformedResponseError,
    ConfigurationError,
)

__all__ = [
    "PayPalSandboxClient",
    "PayPalDisputeError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "RateLimitError",
    "PayPalServerError",
    "NetworkError",
    "TimeoutError",
    "MalformedResponseError",
    "ConfigurationError",
]
