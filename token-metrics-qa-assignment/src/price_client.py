"""
Hyperliquid Price Client

This module provides functionality to fetch cryptocurrency prices from the Hyperliquid API.
It includes retry logic, error handling, and fallback mechanisms for production reliability.
"""

import logging
import time
from typing import Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PriceClientError(Exception):
    """Base exception for price client errors"""
    pass


class CriticalPriceError(PriceClientError):
    """Critical error that should block trading/rebalancing"""
    pass


class RateLimitError(PriceClientError):
    """Rate limit exceeded error"""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class InvalidPriceDataError(CriticalPriceError):
    """Invalid or malformed price data received"""
    pass


class PriceCache:
    """Simple in-memory cache for last known good prices"""
    def __init__(self):
        self._cache = {}

    def get(self, symbol: str) -> Optional[float]:
        """Get last known price for symbol"""
        return self._cache.get(symbol)

    def set(self, symbol: str, price: float):
        """Store last known price for symbol"""
        self._cache[symbol] = price

    def clear(self):
        """Clear all cached prices"""
        self._cache.clear()


# Global cache instance
_price_cache = PriceCache()


def get_session_with_retries(
    retries: int = 3,
    backoff_factor: float = 0.3,
    status_forcelist: tuple = (500, 502, 503, 504)
) -> requests.Session:
    """
    Create a requests session with retry configuration

    Args:
        retries: Number of retry attempts
        backoff_factor: Backoff factor for retries
        status_forcelist: HTTP status codes to retry on

    Returns:
        Configured requests.Session
    """
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_hyperliquid_price(
    symbol: str,
    use_cache_fallback: bool = True,
    fail_fast_on_rate_limit: bool = False,
    session: Optional[requests.Session] = None
) -> float:
    """
    Fetch current price for a symbol from Hyperliquid API

    This function is designed with production-grade error handling:
    - Retries on server errors (500, 502, 503, 504)
    - Validates price data integrity
    - Falls back to cached prices when appropriate
    - Handles rate limiting gracefully

    Args:
        symbol: Trading symbol (e.g., 'BTC', 'ETH')
        use_cache_fallback: Whether to use cached price on certain failures
        fail_fast_on_rate_limit: If True, raises immediately on 429; if False, respects Retry-After
        session: Optional requests session (useful for testing)

    Returns:
        Current price as float

    Raises:
        CriticalPriceError: For invalid data that should block trading
        RateLimitError: When rate limited and fail_fast_on_rate_limit=True
        PriceClientError: For other errors after retries exhausted
    """
    if not symbol or not isinstance(symbol, str):
        raise ValueError(f"Invalid symbol: {symbol}")

    # Use provided session or create one with retries
    if session is None:
        session = get_session_with_retries()

    url = f"https://api.hyperliquid.xyz/info"
    params = {"type": "metaAndAssetCtxs"}

    try:
        response = session.get(url, params=params, timeout=10)

        # Handle rate limiting (429)
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After')
            # Handle non-numeric Retry-After gracefully
            try:
                retry_after_seconds = int(retry_after) if retry_after else 60
            except (ValueError, TypeError):
                logger.warning(f"Invalid Retry-After header: {retry_after}, using default 60s")
                retry_after_seconds = 60

            error_msg = f"Rate limited. Retry after {retry_after_seconds} seconds"
            logger.warning(error_msg)

            if fail_fast_on_rate_limit:
                raise RateLimitError(error_msg, retry_after=retry_after_seconds)

            # Wait and retry
            logger.info(f"Waiting {retry_after_seconds} seconds before retry...")
            time.sleep(retry_after_seconds)
            return get_hyperliquid_price(symbol, use_cache_fallback, fail_fast_on_rate_limit, session)

        # Raise for other HTTP errors (will be caught by retry logic for 5xx)
        response.raise_for_status()

        # Parse response
        data = response.json()

        # Extract price for the symbol from the response
        # This is a simplified example - actual Hyperliquid API structure may differ
        price = None
        if isinstance(data, list) and len(data) > 0:
            for asset in data:
                if isinstance(asset, dict) and asset.get('name') == symbol:
                    price = asset.get('price')
                    break
        elif isinstance(data, dict):
            price = data.get('price')

        # Validate price data
        if price is None:
            error_msg = f"Price field missing for symbol {symbol}"
            logger.error(error_msg)

            # Try cache fallback
            if use_cache_fallback:
                cached_price = _price_cache.get(symbol)
                if cached_price is not None:
                    logger.warning(f"Using cached price for {symbol}: {cached_price}")
                    return cached_price

            raise InvalidPriceDataError(error_msg)

        # Convert to float and validate
        try:
            price_float = float(price)
        except (ValueError, TypeError) as e:
            raise InvalidPriceDataError(f"Invalid price format for {symbol}: {price}") from e

        # Validate price is positive
        if price_float <= 0:
            error_msg = f"Invalid price value for {symbol}: {price_float} (must be positive)"
            logger.error(error_msg)

            # Negative or zero prices are CRITICAL - do not use cache
            raise CriticalPriceError(error_msg)

        # Cache the valid price
        _price_cache.set(symbol, price_float)
        logger.info(f"Successfully fetched price for {symbol}: {price_float}")

        return price_float

    except (RateLimitError, CriticalPriceError, InvalidPriceDataError):
        # Re-raise our custom exceptions
        raise

    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to fetch price for {symbol} after retries: {str(e)}"
        logger.error(error_msg)

        # Try cache fallback for network errors
        if use_cache_fallback:
            cached_price = _price_cache.get(symbol)
            if cached_price is not None:
                logger.warning(f"Using cached price for {symbol} due to network error: {cached_price}")
                return cached_price

        raise PriceClientError(error_msg) from e

    except Exception as e:
        error_msg = f"Unexpected error fetching price for {symbol}: {str(e)}"
        logger.error(error_msg)
        raise PriceClientError(error_msg) from e


def clear_price_cache():
    """Clear the price cache - useful for testing"""
    _price_cache.clear()
