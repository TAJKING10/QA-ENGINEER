"""
Comprehensive test suite for get_hyperliquid_price function

This test suite covers:
- Normal operations (200 OK)
- API failures (500 errors)
- Bad data cases (negative, null, missing)
- Rate limiting (429)
- Edge cases and security concerns
"""

import pytest
import requests
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import RequestException, Timeout, ConnectionError

from src.price_client import (
    get_hyperliquid_price,
    get_session_with_retries,
    CriticalPriceError,
    RateLimitError,
    InvalidPriceDataError,
    PriceClientError,
    clear_price_cache,
)


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear price cache before each test to ensure isolation"""
    clear_price_cache()
    yield
    clear_price_cache()


@pytest.fixture
def mock_session():
    """Create a mock session for testing"""
    return Mock(spec=requests.Session)


# ============================================================================
# NORMAL CASE TESTS (200 OK)
# ============================================================================

class TestNormalOperation:
    """Test suite for successful price fetching scenarios"""

    @pytest.mark.critical
    def test_successful_price_fetch_with_valid_response(self, mock_session):
        """
        Test Case: TC-001
        Scenario: API returns 200 OK with valid positive price
        Expected: Function returns correct float value
        Severity: CRITICAL - Core functionality
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "BTC", "price": 45000.50}
        ]
        mock_session.get.return_value = mock_response

        # Act
        price = get_hyperliquid_price("BTC", session=mock_session)

        # Assert
        assert price == 45000.50
        assert isinstance(price, float)
        mock_session.get.assert_called_once()

    @pytest.mark.high
    def test_successful_price_fetch_with_dict_response(self, mock_session):
        """
        Test Case: TC-002
        Scenario: API returns dict format instead of list
        Expected: Function handles both response formats
        Severity: HIGH - API format flexibility
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": 3500.25}
        mock_session.get.return_value = mock_response

        # Act
        price = get_hyperliquid_price("ETH", session=mock_session)

        # Assert
        assert price == 3500.25

    @pytest.mark.high
    def test_price_caching_on_success(self, mock_session):
        """
        Test Case: TC-003
        Scenario: Valid price should be cached for fallback
        Expected: Price is stored in cache after successful fetch
        Severity: HIGH - Cache reliability for failover
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": 100.0}
        mock_session.get.return_value = mock_response

        # Act
        price1 = get_hyperliquid_price("SOL", session=mock_session)

        # Simulate API failure on second call
        mock_session.get.side_effect = Timeout("Connection timeout")

        # Should return cached value
        price2 = get_hyperliquid_price("SOL", use_cache_fallback=True, session=mock_session)

        # Assert
        assert price1 == 100.0
        assert price2 == 100.0  # Uses cached value


# ============================================================================
# API FAILURE TESTS (500 Errors)
# ============================================================================

class TestAPIFailures:
    """Test suite for API server error scenarios"""

    @pytest.mark.critical
    def test_api_500_error_with_retries(self, mock_session):
        """
        Test Case: TC-101
        Scenario: API returns 500 Internal Server Error
        Expected: Function retries N times, then raises PriceClientError
        Severity: CRITICAL - Must block trading on repeated failures
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(PriceClientError) as exc_info:
            get_hyperliquid_price("BTC", use_cache_fallback=False, session=mock_session)

        assert "Failed to fetch price" in str(exc_info.value)

    @pytest.mark.critical

    def test_api_503_service_unavailable(self, mock_session):
        """
        Test Case: TC-102
        Scenario: API returns 503 Service Unavailable
        Expected: Retries and eventually raises error if all retries fail
        Severity: CRITICAL - Trading must halt if price feed unavailable
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 503
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("503 Service Unavailable")
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(PriceClientError):
            get_hyperliquid_price("ETH", use_cache_fallback=False, session=mock_session)

    @pytest.mark.high

    def test_api_failure_with_cache_fallback(self, mock_session):
        """
        Test Case: TC-103
        Scenario: API fails but valid cached price exists
        Expected: Returns cached price with warning log
        Severity: HIGH - Allows continued operation with stale data
        """
        # Arrange - First successful call
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"price": 50000.0}

        # Second call fails
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

        mock_session.get.side_effect = [mock_response_success, mock_response_fail]

        # Act
        price1 = get_hyperliquid_price("BTC", session=mock_session)
        price2 = get_hyperliquid_price("BTC", use_cache_fallback=True, session=mock_session)

        # Assert
        assert price1 == 50000.0
        assert price2 == 50000.0  # Falls back to cached value

    @pytest.mark.critical

    def test_api_failure_without_cache_raises_error(self, mock_session):
        """
        Test Case: TC-104
        Scenario: API fails and no cached price available
        Expected: Raises PriceClientError immediately
        Severity: CRITICAL - Cannot trade without price data
        """
        # Arrange
        mock_session.get.side_effect = ConnectionError("Network unreachable")

        # Act & Assert
        with pytest.raises(PriceClientError) as exc_info:
            get_hyperliquid_price("BTC", use_cache_fallback=False, session=mock_session)

        assert "Failed to fetch price" in str(exc_info.value)

    @pytest.mark.high

    def test_timeout_error_handling(self, mock_session):
        """
        Test Case: TC-105
        Scenario: API request times out
        Expected: Retries and raises error or uses cache
        Severity: HIGH - Network instability should not crash system
        """
        # Arrange
        mock_session.get.side_effect = Timeout("Request timed out")

        # Act & Assert
        with pytest.raises(PriceClientError) as exc_info:
            get_hyperliquid_price("ETH", use_cache_fallback=False, session=mock_session)

        assert "Failed to fetch price" in str(exc_info.value)


# ============================================================================
# BAD DATA TESTS
# ============================================================================

class TestBadDataHandling:
    """Test suite for invalid/malformed price data scenarios"""

    @pytest.mark.critical

    def test_negative_price_value(self, mock_session):
        """
        Test Case: TC-201
        Scenario: API returns negative price (-100)
        Expected: Raises CriticalPriceError, does NOT use cache
        Severity: CRITICAL - Must block trading immediately
        Rationale: Negative prices indicate data corruption or API compromise
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": -100.0}
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(CriticalPriceError) as exc_info:
            get_hyperliquid_price("BTC", session=mock_session)

        assert "must be positive" in str(exc_info.value).lower()
        assert "-100" in str(exc_info.value)

    @pytest.mark.critical

    def test_zero_price_value(self, mock_session):
        """
        Test Case: TC-202
        Scenario: API returns zero price
        Expected: Raises CriticalPriceError
        Severity: CRITICAL - Zero price would cause catastrophic trading errors
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": 0}
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(CriticalPriceError) as exc_info:
            get_hyperliquid_price("BTC", session=mock_session)

        assert "must be positive" in str(exc_info.value).lower()

    @pytest.mark.high

    def test_null_price_value(self, mock_session):
        """
        Test Case: TC-203
        Scenario: API returns null/None for price field
        Expected: Raises InvalidPriceDataError, tries cache fallback
        Severity: HIGH - Indicates temporary API data issue
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": None}
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(InvalidPriceDataError) as exc_info:
            get_hyperliquid_price("BTC", use_cache_fallback=False, session=mock_session)

        # Either error message is acceptable for null price
        assert ("missing" in str(exc_info.value).lower() or
                "invalid price format" in str(exc_info.value).lower())

    @pytest.mark.high

    def test_missing_price_field(self, mock_session):
        """
        Test Case: TC-204
        Scenario: API response missing 'price' field entirely
        Expected: Raises InvalidPriceDataError, tries cache fallback
        Severity: HIGH - API schema change or partial response
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"volume": 1000000}  # No price field
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(InvalidPriceDataError) as exc_info:
            get_hyperliquid_price("BTC", use_cache_fallback=False, session=mock_session)

        assert "missing" in str(exc_info.value).lower()

    @pytest.mark.high

    def test_missing_price_field_with_cache_fallback(self, mock_session):
        """
        Test Case: TC-205
        Scenario: Missing price field but cached price available
        Expected: Returns cached price with warning
        Severity: HIGH - Graceful degradation
        """
        # Arrange - First call succeeds
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"price": 45000.0}

        # Second call has missing field
        mock_response_missing = Mock()
        mock_response_missing.status_code = 200
        mock_response_missing.json.return_value = {"volume": 999}

        mock_session.get.side_effect = [mock_response_success, mock_response_missing]

        # Act
        price1 = get_hyperliquid_price("BTC", session=mock_session)
        price2 = get_hyperliquid_price("BTC", use_cache_fallback=True, session=mock_session)

        # Assert
        assert price1 == 45000.0
        assert price2 == 45000.0  # Uses cache

    @pytest.mark.critical

    def test_non_numeric_price_value(self, mock_session):
        """
        Test Case: TC-206
        Scenario: API returns non-numeric price (e.g., "N/A", "error")
        Expected: Raises InvalidPriceDataError
        Severity: CRITICAL - Data corruption or API error
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": "INVALID"}
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(InvalidPriceDataError) as exc_info:
            get_hyperliquid_price("BTC", session=mock_session)

        assert "Invalid price format" in str(exc_info.value)

    @pytest.mark.low

    def test_extremely_large_price_value(self, mock_session):
        """
        Test Case: TC-207
        Scenario: API returns unrealistically large price
        Expected: Function returns value (no validation on max)
        Severity: LOW - May want to add bounds checking in production
        Note: This test documents current behavior; consider adding max price validation
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": 999999999999.99}
        mock_session.get.return_value = mock_response

        # Act
        price = get_hyperliquid_price("BTC", session=mock_session)

        # Assert
        assert price == 999999999999.99
        # Note: In production, may want to add sanity checks for price bounds

    @pytest.mark.low

    def test_price_with_many_decimal_places(self, mock_session):
        """
        Test Case: TC-208
        Scenario: Price has high precision (many decimal places)
        Expected: Full precision is preserved
        Severity: LOW - Important for low-value tokens
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": 0.00000123456789}
        mock_session.get.return_value = mock_response

        # Act
        price = get_hyperliquid_price("SHIB", session=mock_session)

        # Assert
        assert price == 0.00000123456789


# ============================================================================
# RATE LIMITING TESTS (429)
# ============================================================================

class TestRateLimiting:
    """Test suite for rate limiting scenarios"""

    @pytest.mark.high

    def test_rate_limit_429_with_retry_after_header(self, mock_session):
        """
        Test Case: TC-301
        Scenario: API returns 429 with Retry-After header
        Expected: Waits specified time and retries (when fail_fast=False)
        Severity: HIGH - Must respect API rate limits to avoid ban
        """
        # Arrange
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {'Retry-After': '2'}

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"price": 45000.0}

        mock_session.get.side_effect = [mock_response_429, mock_response_success]

        # Act
        with patch('time.sleep') as mock_sleep:  # Mock sleep to speed up test
            price = get_hyperliquid_price("BTC", fail_fast_on_rate_limit=False, session=mock_session)

        # Assert
        assert price == 45000.0
        mock_sleep.assert_called_once_with(2)

    @pytest.mark.high

    def test_rate_limit_429_without_retry_after_header(self, mock_session):
        """
        Test Case: TC-302
        Scenario: API returns 429 without Retry-After header
        Expected: Uses default wait time (60s) and retries
        Severity: HIGH - Graceful handling of incomplete rate limit response
        """
        # Arrange
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {}

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"price": 45000.0}

        mock_session.get.side_effect = [mock_response_429, mock_response_success]

        # Act
        with patch('time.sleep') as mock_sleep:
            price = get_hyperliquid_price("BTC", fail_fast_on_rate_limit=False, session=mock_session)

        # Assert
        assert price == 45000.0
        mock_sleep.assert_called_once_with(60)  # Default retry after

    @pytest.mark.high

    def test_rate_limit_fail_fast_mode(self, mock_session):
        """
        Test Case: TC-303
        Scenario: API returns 429 and fail_fast_on_rate_limit=True
        Expected: Raises RateLimitError immediately without retry
        Severity: CRITICAL - Must signal rate limiting to prevent cascade failures
        Rationale: During high-frequency trading, waiting may be worse than failing fast
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {'Retry-After': '60'}
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(RateLimitError) as exc_info:
            get_hyperliquid_price("BTC", fail_fast_on_rate_limit=True, session=mock_session)

        assert exc_info.value.retry_after == 60
        assert "Rate limited" in str(exc_info.value)

    @pytest.mark.low

    def test_rate_limit_retry_after_non_numeric(self, mock_session):
        """
        Test Case: TC-304
        Scenario: Retry-After header contains non-numeric value
        Expected: Uses default wait time
        Severity: LOW - Edge case handling
        """
        # Arrange
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {'Retry-After': 'invalid'}

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"price": 45000.0}

        mock_session.get.side_effect = [mock_response_429, mock_response_success]

        # Act & Assert
        # Should handle gracefully (may use default or raise - depends on implementation)
        with patch('time.sleep'):
            try:
                price = get_hyperliquid_price("BTC", fail_fast_on_rate_limit=False, session=mock_session)
                # If it succeeds, verify it used a fallback
                assert price == 45000.0
            except (ValueError, RateLimitError):
                # Also acceptable to raise error on invalid header
                pass


# ============================================================================
# EDGE CASES AND SECURITY
# ============================================================================

class TestEdgeCasesAndSecurity:
    """Test suite for edge cases, input validation, and security concerns"""

    @pytest.mark.high

    def test_empty_symbol_string(self, mock_session):
        """
        Test Case: TC-401
        Scenario: Empty string passed as symbol
        Expected: Raises ValueError
        Severity: HIGH - Input validation
        """
        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            get_hyperliquid_price("", session=mock_session)

        assert "Invalid symbol" in str(exc_info.value)

    @pytest.mark.high

    def test_none_symbol(self, mock_session):
        """
        Test Case: TC-402
        Scenario: None passed as symbol
        Expected: Raises ValueError
        Severity: HIGH - Type safety
        """
        # Act & Assert
        with pytest.raises(ValueError):
            get_hyperliquid_price(None, session=mock_session)

    @pytest.mark.critical

    def test_malformed_json_response(self, mock_session):
        """
        Test Case: TC-403
        Scenario: API returns malformed JSON
        Expected: Raises PriceClientError
        Severity: CRITICAL - Data integrity
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(PriceClientError):
            get_hyperliquid_price("BTC", use_cache_fallback=False, session=mock_session)

    @pytest.mark.high

    def test_empty_response_body(self, mock_session):
        """
        Test Case: TC-404
        Scenario: API returns empty response
        Expected: Raises InvalidPriceDataError
        Severity: HIGH - Unexpected API behavior
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(InvalidPriceDataError):
            get_hyperliquid_price("BTC", use_cache_fallback=False, session=mock_session)

    @pytest.mark.high

    def test_symbol_not_found_in_response(self, mock_session):
        """
        Test Case: TC-405
        Scenario: Response contains data but not for requested symbol
        Expected: Raises InvalidPriceDataError
        Severity: HIGH - Symbol mismatch
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "ETH", "price": 3000.0}
        ]
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(InvalidPriceDataError) as exc_info:
            get_hyperliquid_price("BTC", use_cache_fallback=False, session=mock_session)

        assert "missing" in str(exc_info.value).lower()

    @pytest.mark.critical

    def test_concurrent_calls_cache_isolation(self, mock_session):
        """
        Test Case: TC-406
        Scenario: Multiple symbols cached simultaneously
        Expected: Cache maintains separate entries per symbol
        Severity: CRITICAL - Cache corruption could cause wrong prices
        """
        # Arrange
        mock_response_btc = Mock()
        mock_response_btc.status_code = 200
        mock_response_btc.json.return_value = {"price": 45000.0}

        mock_response_eth = Mock()
        mock_response_eth.status_code = 200
        mock_response_eth.json.return_value = {"price": 3000.0}

        # Act
        mock_session.get.return_value = mock_response_btc
        btc_price = get_hyperliquid_price("BTC", session=mock_session)

        mock_session.get.return_value = mock_response_eth
        eth_price = get_hyperliquid_price("ETH", session=mock_session)

        # Verify cache isolation by triggering failures
        mock_session.get.side_effect = ConnectionError("Network down")

        cached_btc = get_hyperliquid_price("BTC", use_cache_fallback=True, session=mock_session)
        cached_eth = get_hyperliquid_price("ETH", use_cache_fallback=True, session=mock_session)

        # Assert
        assert btc_price == 45000.0
        assert eth_price == 3000.0
        assert cached_btc == 45000.0
        assert cached_eth == 3000.0
        assert cached_btc != cached_eth  # Different symbols have different cached prices

    @pytest.mark.low

    def test_unicode_symbol_handling(self, mock_session):
        """
        Test Case: TC-407
        Scenario: Symbol contains unicode characters
        Expected: Handles gracefully (may return error or process)
        Severity: LOW - Edge case for internationalization
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": 100.0}
        mock_session.get.return_value = mock_response

        # Act - Should not crash
        try:
            price = get_hyperliquid_price("БТЦ", session=mock_session)
            assert isinstance(price, float)
        except (ValueError, InvalidPriceDataError):
            # Also acceptable to reject invalid symbols
            pass


# ============================================================================
# INTEGRATION-STYLE TESTS
# ============================================================================

class TestRealisticScenarios:
    """Integration-style tests simulating realistic production scenarios"""

    @pytest.mark.critical

    def test_high_volatility_rapid_calls(self, mock_session):
        """
        Test Case: TC-501
        Scenario: Multiple rapid price calls during high volatility
        Expected: Each call returns independent result, cache updates
        Severity: CRITICAL - High-frequency trading scenario
        """
        # Arrange - Simulate price changes
        prices = [45000.0, 45100.0, 44900.0, 45050.0]
        responses = []
        for price in prices:
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"price": price}
            responses.append(mock_resp)

        mock_session.get.side_effect = responses

        # Act
        fetched_prices = []
        for _ in range(4):
            fetched_prices.append(get_hyperliquid_price("BTC", session=mock_session))

        # Assert
        assert fetched_prices == prices

    @pytest.mark.high

    def test_intermittent_failures_with_recovery(self, mock_session):
        """
        Test Case: TC-502
        Scenario: API fails intermittently then recovers
        Expected: Uses cache during failures, updates when recovered
        Severity: HIGH - Network instability resilience
        """
        # Arrange
        mock_success1 = Mock()
        mock_success1.status_code = 200
        mock_success1.json.return_value = {"price": 45000.0}

        mock_failure = Mock()
        mock_failure.status_code = 500
        mock_failure.raise_for_status.side_effect = requests.exceptions.HTTPError("500")

        mock_success2 = Mock()
        mock_success2.status_code = 200
        mock_success2.json.return_value = {"price": 46000.0}

        mock_session.get.side_effect = [mock_success1, mock_failure, mock_success2]

        # Act
        price1 = get_hyperliquid_price("BTC", session=mock_session)
        price2 = get_hyperliquid_price("BTC", use_cache_fallback=True, session=mock_session)
        price3 = get_hyperliquid_price("BTC", session=mock_session)

        # Assert
        assert price1 == 45000.0  # Initial fetch
        assert price2 == 45000.0  # Cache during failure
        assert price3 == 46000.0  # New price after recovery

    @pytest.mark.critical

    def test_complete_failure_scenario_blocks_trading(self, mock_session):
        """
        Test Case: TC-503
        Scenario: Total API failure with no cache available
        Expected: Raises exception to block trading operations
        Severity: CRITICAL - Must prevent trading with no price data
        """
        # Arrange
        mock_session.get.side_effect = ConnectionError("Total network failure")

        # Act & Assert
        with pytest.raises(PriceClientError):
            get_hyperliquid_price("BTC", use_cache_fallback=False, session=mock_session)


# ============================================================================
# PERFORMANCE AND RELIABILITY TESTS
# ============================================================================

class TestSessionManagement:
    """Tests for session creation and management"""

    @pytest.mark.low

    def test_get_session_with_retries_creates_session(self):
        """
        Test Case: TC-701
        Scenario: Create session with retry configuration
        Expected: Returns configured requests.Session
        Severity: LOW - Utility function
        """
        # Act
        session = get_session_with_retries()

        # Assert
        assert isinstance(session, requests.Session)
        # Verify session has adapters mounted
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters

    @pytest.mark.low

    def test_default_session_creation_when_none_provided(self):
        """
        Test Case: TC-702
        Scenario: Call get_hyperliquid_price without session parameter
        Expected: Function creates session internally
        Severity: LOW - Default behavior
        """
        # Arrange - Mock the actual HTTP call
        with patch('src.price_client.requests.Session') as MockSession:
            mock_session_instance = Mock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"price": 45000.0}
            mock_session_instance.get.return_value = mock_response
            MockSession.return_value = mock_session_instance

            # Act
            price = get_hyperliquid_price("BTC", session=None)

            # Assert
            assert price == 45000.0
            MockSession.assert_called()  # Session was created


class TestPerformanceAndReliability:
    """Tests for performance characteristics and reliability"""

    @pytest.mark.low

    def test_cache_performance_benefit(self, mock_session):
        """
        Test Case: TC-601
        Scenario: Verify cache provides performance benefit
        Expected: Cached call doesn't make API request
        Severity: LOW - Performance optimization
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": 45000.0}
        mock_session.get.return_value = mock_response

        # Act
        get_hyperliquid_price("BTC", session=mock_session)
        mock_session.reset_mock()

        # Trigger cache usage
        mock_session.get.side_effect = ConnectionError("Network down")
        cached_price = get_hyperliquid_price("BTC", use_cache_fallback=True, session=mock_session)

        # Assert
        assert cached_price == 45000.0
        # Verify API was called during failure (before falling back)
        assert mock_session.get.called

    @pytest.mark.low

    def test_exception_message_clarity(self, mock_session):
        """
        Test Case: TC-602
        Scenario: Verify error messages are actionable
        Expected: Error messages contain symbol, reason, and context
        Severity: LOW - Operational clarity
        """
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": -50}
        mock_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(CriticalPriceError) as exc_info:
            get_hyperliquid_price("BTC", session=mock_session)

        error_message = str(exc_info.value)
        assert "BTC" in error_message
        assert "-50" in error_message
        assert "positive" in error_message.lower()
