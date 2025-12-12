# Test Plan: Hyperliquid Price Client

**Version:** 1.0
**Author:** QA Engineering Candidate
**Date:** 2024
**Target:** `get_hyperliquid_price()` function and associated error handling

---

## 1. Executive Summary

This test plan defines the comprehensive testing strategy for the `get_hyperliquid_price()` function, which is **critical infrastructure** for Token Metrics' trading and rebalancing operations. Since this function directly affects user funds, we employ a **fail-safe** testing approach with strict severity classifications.

### Key Principles
- **Safety First**: Invalid price data must block trading operations
- **Fail-Safe Defaults**: When in doubt, halt operations rather than proceed with uncertain data
- **Graceful Degradation**: Use cached data only when safe to do so
- **Rate Limit Respect**: Prevent API bans that would cause extended outages

---

## 2. Severity Classification Framework

### 2.1 Severity Definitions

| Severity | Impact | Response Required | Examples |
|----------|--------|-------------------|----------|
| **CRITICAL** | Could cause financial loss or system halt | Block trading/rebalancing immediately | Negative prices, zero prices, total API failure |
| **HIGH** | Degrades functionality but fail-safes engage | Alert + log, use fallback if safe | Rate limiting, missing data with cache available |
| **LOW** | Minor issues with minimal impact | Log for monitoring | Edge cases, performance optimizations |

### 2.2 Decision Matrix: Block vs Continue

```
┌─────────────────────────────────────────────────────────────┐
│ BLOCK TRADING (CRITICAL)                                    │
├─────────────────────────────────────────────────────────────┤
│ • Negative price values                                     │
│ • Zero price values                                         │
│ • Total API failure with no cache                           │
│ • Corrupted/malformed data                                  │
│ • Symbol mismatch (requested BTC, got ETH price)            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ ALERT + FAIL-SAFE (HIGH)                                    │
├─────────────────────────────────────────────────────────────┤
│ • Missing price field with cache available                  │
│ • Null price with cache available                           │
│ • Temporary API errors (500, 503) with cache available      │
│ • Rate limiting (429) - respect Retry-After                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ LOG + CONTINUE (LOW)                                        │
├─────────────────────────────────────────────────────────────┤
│ • Successfully fetched price with high decimal precision    │
│ • Cache hit on subsequent calls                             │
│ • Retry succeeded after transient network error             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Test Cases

### 3.1 Normal Operation Tests (200 OK)

#### TC-001: Valid Price Fetch
**Scenario:** API returns 200 OK with valid positive price
**Test Data:** `{"name": "BTC", "price": 45000.50}`
**Expected Behavior:**
- Function returns `45000.50` as float
- Price is cached for future fallback
- No errors or warnings logged

**Severity:** **CRITICAL**
**Rationale:** Core functionality - if this fails, entire system is broken

---

#### TC-002: Alternative Response Format
**Scenario:** API returns dict instead of list format
**Test Data:** `{"price": 3500.25}`
**Expected Behavior:**
- Function handles both formats gracefully
- Returns correct price

**Severity:** HIGH
**Rationale:** API format changes should not break system

---

#### TC-003: Price Caching
**Scenario:** Valid price should be cached after successful fetch
**Expected Behavior:**
- First call stores price in cache
- Subsequent failures can use cached value
- Cache is isolated per symbol

**Severity:** HIGH
**Rationale:** Cache is critical for fault tolerance

---

### 3.2 API Failure Tests (5xx Errors)

#### TC-101: 500 Internal Server Error
**Scenario:** API returns 500 error
**Expected Behavior:**
- Retry 3 times with exponential backoff
- If all retries fail: raise `PriceClientError`
- If cache available: log error + return cached value

**Severity:** **CRITICAL**
**Rationale:** **Must block trading if no valid price available**
- Without cache: Cannot proceed safely
- With cache: Can continue with degraded mode (alert operators)

---

#### TC-102: 503 Service Unavailable
**Scenario:** API service is down
**Expected Behavior:**
- Same retry logic as TC-101
- Raise error if all retries exhausted and no cache

**Severity:** **CRITICAL**
**Rationale:** Complete service outage - must halt trading without reliable data

---

#### TC-103: Network Timeout
**Scenario:** API request times out
**Expected Behavior:**
- Retry with backoff
- Use cache if available
- Raise `PriceClientError` if no cache

**Severity:** HIGH
**Rationale:** Transient network issues are common; cache provides continuity

---

#### TC-104: API Failure Without Cache
**Scenario:** First-ever price fetch fails (no cached data)
**Expected Behavior:**
- Raise `PriceClientError` immediately
- **Block any trading operation**
- Alert operators

**Severity:** **CRITICAL**
**Rationale:** Cannot trade without any price data

---

### 3.3 Bad Data Tests

#### TC-201: Negative Price Value
**Scenario:** API returns `price: -100`
**Expected Behavior:**
- **Immediately raise `CriticalPriceError`**
- **Do NOT use cache** (this is data corruption, not transient error)
- **Block all trading operations**
- Alert security team (possible API compromise)

**Severity:** **CRITICAL**
**Rationale:**
- Negative prices indicate severe data corruption or API compromise
- Trading with negative prices would cause catastrophic financial errors
- This is NOT a transient error - using cached "good" data masks a critical problem
- **Philosophy:** Fail loudly on data integrity violations

---

#### TC-202: Zero Price Value
**Scenario:** API returns `price: 0`
**Expected Behavior:**
- Raise `CriticalPriceError`
- Block trading operations
- Do not use cache

**Severity:** **CRITICAL**
**Rationale:** Zero price would cause division errors and invalid trade calculations

---

#### TC-203: Null Price Value
**Scenario:** API returns `price: null`
**Expected Behavior:**
- Raise `InvalidPriceDataError`
- Attempt cache fallback if available
- If no cache: block trading

**Severity:** HIGH (with cache) / **CRITICAL** (without cache)
**Rationale:**
- Null indicates temporary data unavailability (not corruption)
- Cache fallback is appropriate here
- Without cache: cannot proceed

---

#### TC-204: Missing Price Field
**Scenario:** API response lacks `price` field entirely
**Expected Behavior:**
- Raise `InvalidPriceDataError`
- Try cache fallback
- Log alert (possible API schema change)

**Severity:** HIGH (with cache) / **CRITICAL** (without cache)
**Rationale:** May indicate API version change; needs investigation but cache is safe fallback

---

#### TC-205: Non-Numeric Price
**Scenario:** API returns `price: "INVALID"` or `price: "N/A"`
**Expected Behavior:**
- Raise `InvalidPriceDataError`
- Do not use cache (data corruption)
- Block trading

**Severity:** **CRITICAL**
**Rationale:** Similar to negative price - indicates data corruption

---

#### TC-206: Symbol Mismatch
**Scenario:** Request BTC but response contains ETH data
**Expected Behavior:**
- Raise `InvalidPriceDataError`
- **Critical: Do NOT return wrong symbol's price**
- Block trading

**Severity:** **CRITICAL**
**Rationale:** Returning wrong symbol's price could cause massive financial loss

---

### 3.4 Rate Limiting Tests (429)

#### TC-301: Rate Limit with Retry-After Header
**Scenario:** API returns 429 with `Retry-After: 60`
**Expected Behavior:**
- **If `fail_fast_on_rate_limit=False`:**
  - Wait 60 seconds
  - Retry once
  - If success: return price
  - If still rate limited: raise `RateLimitError`

- **If `fail_fast_on_rate_limit=True`:**
  - Immediately raise `RateLimitError` with retry_after value
  - Do NOT wait

**Severity:** HIGH
**Rationale:**
- **During normal operation:** Wait and retry (prevents API ban)
- **During high-frequency trading:** Fail fast (waiting 60s is unacceptable)
- **Philosophy:** Rate limiting is not a data integrity issue - it's a resource constraint

**Why Not Critical?**
- Rate limiting doesn't indicate bad data
- Cache can be used if available
- Waiting and retrying is often the correct behavior

---

#### TC-302: Rate Limit Without Retry-After
**Scenario:** API returns 429 without header
**Expected Behavior:**
- Use default wait time (60 seconds)
- Otherwise same as TC-301

**Severity:** HIGH
**Rationale:** Degraded rate limit response; should still respect limit

---

#### TC-303: Fail-Fast Mode Critical Path
**Scenario:** High-frequency rebalancing operation hits rate limit
**Expected Behavior:**
- Fail fast to allow upstream system to decide strategy
- May choose to: skip this price, use cache, delay rebalance, etc.
- Don't block for 60 seconds

**Severity:** HIGH
**Rationale:** In time-sensitive operations, waiting is worse than signaling failure

---

### 3.5 Edge Cases and Security

#### TC-401: Empty Symbol String
**Scenario:** `get_hyperliquid_price("")`
**Expected Behavior:**
- Raise `ValueError` before making API call
- Clear error message

**Severity:** HIGH
**Rationale:** Input validation prevents wasted API calls

---

#### TC-402: None Symbol
**Scenario:** `get_hyperliquid_price(None)`
**Expected Behavior:**
- Raise `ValueError` with clear message

**Severity:** HIGH
**Rationale:** Type safety prevents runtime errors

---

#### TC-403: Malformed JSON
**Scenario:** API returns invalid JSON
**Expected Behavior:**
- Raise `PriceClientError`
- Try cache if available
- Log parse error

**Severity:** **CRITICAL** (without cache)
**Rationale:** Corrupted response from API

---

#### TC-404: Concurrent Multi-Symbol Cache
**Scenario:** BTC and ETH prices cached simultaneously
**Expected Behavior:**
- Cache maintains separate entries
- **No cache pollution** (BTC request never returns ETH price)
- Thread-safe (if applicable)

**Severity:** **CRITICAL**
**Rationale:** Cache pollution would return wrong prices

---

### 3.6 Realistic Integration Scenarios

#### TC-501: High Volatility Rapid Calls
**Scenario:** Multiple calls within seconds during market crash
**Expected Behavior:**
- Each call returns current price (no stale cache)
- Cache updates on each successful call
- Performance remains acceptable

**Severity:** **CRITICAL**
**Rationale:** During volatility, stale prices cause wrong rebalancing decisions

---

#### TC-502: Intermittent Failures with Recovery
**Scenario:** API fails, recovers, fails again
**Expected Behavior:**
- Use cache during failures
- Update cache when API recovers
- Don't fail permanently after first error

**Severity:** HIGH
**Rationale:** Network instability is common; system must be resilient

---

#### TC-503: Complete Prolonged Outage
**Scenario:** API down for 30+ minutes, cache goes stale
**Expected Behavior:**
- **Decision Point:** Should system:
  - Block trading after N minutes of stale data? (RECOMMENDED)
  - Continue with stale cache? (RISKY)
  - Require manual override? (SAFEST)

**Severity:** **CRITICAL**
**Rationale:** Stale data during high volatility is dangerous
**Recommendation:** Implement cache age check (max 5-10 minutes)

---

## 4. Test Execution Strategy

### 4.1 Test Execution Order
1. **Normal operation tests first** - verify core functionality
2. **Bad data tests** - verify fail-safes work
3. **API failure tests** - verify retry logic
4. **Rate limiting tests** - verify backoff behavior
5. **Edge cases** - verify input validation
6. **Integration scenarios** - verify real-world resilience

### 4.2 Test Data Management
- Use mocks for all API calls (no live API in tests)
- Mock data should reflect real Hyperliquid API structure
- Include edge cases from actual production data

### 4.3 Test Environment
- Python 3.8+
- pytest framework
- Mock/patch for API calls
- CI/CD integration with GitHub Actions

---

## 5. Pass/Fail Criteria

### 5.1 Passing Criteria
- All CRITICAL severity tests pass
- All HIGH severity tests pass
- At least 95% of LOW severity tests pass
- Code coverage > 95%
- No unhandled exceptions in production code

### 5.2 Failing Criteria (Block Merge/Deploy)
- Any CRITICAL test fails
- More than 1 HIGH severity test fails
- Code coverage < 90%
- Any test with "block trading" behavior fails

### 5.3 Warning Criteria (Manual Review Required)
- Any HIGH severity test fails
- Code coverage 90-95%
- Any new untested code paths

---

## 6. Risk Analysis

### 6.1 High-Risk Scenarios

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Negative price returned to trading system | Low | **Catastrophic** | TC-201, TC-202 |
| Cache returns wrong symbol's price | Low | **Catastrophic** | TC-404 |
| API outage with no cache | Medium | **Critical** | TC-104, cache warming strategy |
| Rate limiting causes API ban | Medium | High | TC-301, TC-302, TC-303 |
| Stale cache during high volatility | Medium | High | TC-503, implement cache age limits |

### 6.2 Testing Gaps (Future Work)
1. **Load testing:** Verify performance under 1000 req/sec
2. **Concurrency testing:** Thread safety of cache
3. **Cache expiration:** Currently no TTL on cached prices
4. **Circuit breaker:** Should we stop trying after N failures?
5. **Monitoring integration:** Alerting on repeated failures

---

## 7. Severity Justification Summary

### Why These Specific Severities?

#### CRITICAL Severity Assignments
These failures could cause **direct financial loss** or **system-wide trading halt**:

1. **Negative/Zero Prices (TC-201, TC-202)**
   - Trading with negative prices = financial catastrophe
   - Better to halt all trading than risk this

2. **Total API Failure Without Cache (TC-104)**
   - Cannot trade without price data
   - No safe fallback available

3. **Symbol Mismatch (TC-206)**
   - Returning ETH price when BTC requested = wrong trades
   - Direct financial loss

4. **Cache Pollution (TC-404)**
   - If cache returns wrong symbol's price
   - Silent corruption with massive impact

#### HIGH Severity Assignments
These failures are **serious but have fail-safes**:

1. **Missing Data With Cache (TC-203, TC-204)**
   - Cache provides temporary continuity
   - Not as critical because we have fallback
   - Still needs investigation

2. **Rate Limiting (TC-301)**
   - Doesn't indicate bad data
   - Waiting and retrying is often correct
   - Fail-fast option available for time-sensitive cases

3. **API Failures With Cache (TC-103)**
   - Cache allows degraded operation
   - Alerts trigger investigation
   - Trading can continue cautiously

#### LOW Severity Assignments
These are **edge cases or operational notes**:

1. **Successful Operations (TC-001, TC-002)**
   - These working is expected
   - Important to verify but not "severe"

2. **Performance Optimizations**
   - Cache hits, precision handling
   - Important but not safety-critical

---

## 8. Continuous Improvement

### 8.1 Monitoring Post-Deployment
- Track actual API failure rates
- Measure cache hit rates
- Monitor stale cache age in production
- Alert on repeated critical errors

### 8.2 Test Plan Updates
- Review after each production incident
- Add regression tests for bugs found in prod
- Update severity as system evolves

---

## 9. Appendix: Example Failure Scenarios

### Scenario A: Flash Crash
**Situation:** BTC drops 50% in 2 minutes, API overloaded
**Expected System Behavior:**
1. Attempt to fetch current price (likely rate limited)
2. If rate limited: use cache briefly
3. If cache > 2 minutes old during high volatility: **BLOCK rebalancing**
4. Alert operators

**Tests Covering This:** TC-301, TC-501, TC-503

---

### Scenario B: API Compromise
**Situation:** Hyperliquid API hacked, returns negative prices
**Expected System Behavior:**
1. Detect negative price immediately
2. Raise `CriticalPriceError`
3. **HALT all trading**
4. **Do NOT use cache** (masks the attack)
5. Alert security team

**Tests Covering This:** TC-201, TC-205

---

### Scenario C: Gradual API Degradation
**Situation:** API slowly failing, 10% of requests return 500
**Expected System Behavior:**
1. Retry logic absorbs transient failures
2. Successful requests update cache
3. Failed requests use cache
4. Monitoring alerts on elevated error rate
5. Continue trading with degraded reliability

**Tests Covering This:** TC-101, TC-103, TC-502

---

## 10. Conclusion

This test plan implements a **"safety first"** philosophy appropriate for financial systems:

✅ **Block trading on data integrity violations** (negative prices, corruption)
✅ **Use cache only for transient failures** (network errors, rate limits)
✅ **Fail loudly on critical errors** (no silent failures)
✅ **Respect rate limits** (prevent API bans)
✅ **Provide multiple fail-safes** (retries, cache, alerts)

The severity classifications ensure that:
- Merge-blocking failures are truly critical
- High-severity issues get prompt attention
- Low-severity items don't create noise

This enables **confident deployment** while protecting user funds.
