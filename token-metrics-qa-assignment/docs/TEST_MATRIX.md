# Test Matrix: TM100 Rebalance Process

**Version:** 1.0
**Scope:** End-to-end testing strategy for TM100 portfolio rebalancing
**Dependencies:** Price data from Hyperliquid API (via `get_hyperliquid_price`)

---

## 1. Overview

This document defines a comprehensive test matrix for the **TM100 rebalance process**, which depends on accurate price data to calculate portfolio allocations and execute trades.

### System Architecture (Simplified)
```
┌─────────────────────────────────────────────────────────────────┐
│                     TM100 REBALANCE FLOW                        │
└─────────────────────────────────────────────────────────────────┘

[UI: User Initiates Rebalance]
         ↓
[API: Get Current Portfolio Holdings]
         ↓
[Price Service: Fetch Current Prices] ← get_hyperliquid_price()
         ↓
[Calculation Engine: Compute Target Allocations]
         ↓
[Smart Contracts: Execute Trades on-chain]
         ↓
[UI: Display Rebalance Results]
```

---

## 2. Test Pyramid Strategy

```
                    ┌─────────────────┐
                    │   E2E Tests     │  ← 10% (Slow, Expensive)
                    │   UI + API +    │
                    │   Contracts     │
                ┌───┴─────────────────┴───┐
                │   Integration Tests     │  ← 30% (Medium Speed)
                │   API + Price Service   │
            ┌───┴─────────────────────────┴───┐
            │       Unit Tests                │  ← 60% (Fast, Cheap)
            │   get_hyperliquid_price()       │
            │   Calculation Logic             │
        ┌───┴─────────────────────────────────┴───┐
        │          Static Analysis                │
        │      Linting, Type Checking             │
        └─────────────────────────────────────────┘
```

---

## 3. Test Matrix

### 3.1 Unit Tests (Layer 1)

| Component | Test Type | Test Cases | Pass Criteria | Failure Action |
|-----------|-----------|------------|---------------|----------------|
| **Price Fetcher** | Function-level | • Valid price (200 OK)<br>• API errors (500)<br>• Bad data (negative, null)<br>• Rate limits (429) | All critical paths covered | **BLOCK MERGE** |
| **Allocation Calculator** | Logic tests | • Valid portfolio splits<br>• Edge case: 100% single asset<br>• Rounding errors<br>• Min trade size thresholds | Calculations match spec | **BLOCK MERGE** |
| **Portfolio Validator** | Data validation | • Valid holdings format<br>• Missing symbols<br>• Negative balances<br>• Empty portfolio | Invalid data rejected | **BLOCK MERGE** |
| **Trade Executor** | Mock contracts | • Successful swap<br>• Slippage limits<br>• Insufficient balance<br>• Contract reverts | Error handling correct | **BLOCK MERGE** |

**Coverage Target:** >95%
**Execution Time:** <30 seconds
**Frequency:** On every commit (pre-commit hook)

---

### 3.2 API Integration Tests (Layer 2)

| Integration | Test Scenario | Dependencies | Pass Criteria | Failure Action |
|-------------|---------------|--------------|---------------|----------------|
| **Price Service ↔ API** | • Fetch multiple symbols<br>• Handle partial failures<br>• Cache behavior<br>• Concurrent requests | Mock Hyperliquid API | Response format correct,<br>Cache works | **BLOCK PR MERGE** |
| **Rebalance API ↔ Price Service** | • Calculate rebalance with live prices<br>• Handle price fetch failures<br>• Stale price detection | Mock Price Service | Graceful degradation | **BLOCK PR MERGE** |
| **Trade Execution ↔ Contracts** | • Simulate on-chain trades<br>• Gas estimation<br>• Transaction signing | Testnet or Hardhat | Transactions validate | **BLOCK DEPLOYMENT** |
| **Database ↔ API** | • Store rebalance history<br>• Retrieve past allocations<br>• Concurrent writes | Test DB instance | Data integrity | **BLOCK PR MERGE** |

**Coverage Target:** >85%
**Execution Time:** 2-5 minutes
**Frequency:** On every pull request
**Environment:** Staging API + Testnet

---

### 3.3 End-to-End Tests (Layer 3)

| User Flow | Test Steps | Systems Involved | Pass Criteria | Failure Action |
|-----------|------------|------------------|---------------|----------------|
| **Successful Rebalance** | 1. User logs in (UI)<br>2. Views portfolio (API)<br>3. Initiates rebalance (UI)<br>4. Prices fetched (Price Service)<br>5. Trades executed (Contracts)<br>6. UI shows success | UI + API + Price + Contracts | Allocations match target,<br>Funds transferred | **BLOCK DEPLOYMENT** |
| **Rebalance During Price Failure** | 1. User initiates rebalance<br>2. Price API returns 500<br>3. System uses cache<br>4. Warning displayed<br>5. User confirms<br>6. Rebalance completes | UI + API + Price (mocked failure) | Cache used,<br>Warning shown,<br>Rebalance completes | **MANUAL REVIEW** |
| **Rebalance with Insufficient Funds** | 1. User with $100 portfolio<br>2. Requests rebalance<br>3. Gas fees > available balance<br>4. Error displayed clearly | UI + API + Contracts | Clear error message,<br>No partial execution | **BLOCK DEPLOYMENT** |
| **High Volatility Scenario** | 1. Initiate rebalance<br>2. Prices change >5% during execution<br>3. Slippage protection triggers<br>4. User prompted to retry | UI + API + Price + Contracts | Slippage protection works,<br>No loss from outdated prices | **BLOCK DEPLOYMENT** |
| **Rate Limit Handling** | 1. User initiates rebalance<br>2. Price API rate limits (429)<br>3. System waits per Retry-After<br>4. Rebalance completes after delay | UI + API + Price | Respects rate limit,<br>Eventually succeeds | **MANUAL REVIEW** |
| **API Compromise (Negative Price)** | 1. Mock API returns negative price<br>2. System detects corruption<br>3. **Halts rebalance**<br>4. Alerts admin<br>5. Clear error to user | UI + API + Price (mocked attack) | **Trading BLOCKED**,<br>Alert sent,<br>User not stuck | **BLOCK DEPLOYMENT** |

**Coverage Target:** Critical paths only
**Execution Time:** 10-20 minutes
**Frequency:** Before each deployment
**Environment:** Staging (mirrors production)

---

## 4. Test Scenarios by Risk Level

### 4.1 CRITICAL Risk Scenarios (Must Have E2E Tests)

| Scenario | What Could Go Wrong | Test Coverage | Mitigation |
|----------|---------------------|---------------|------------|
| **Negative prices cause incorrect trades** | User sells at negative value, infinite losses | E2E test with mocked negative price | System halts, user alerted |
| **Stale prices during high volatility** | Rebalance uses 5-min-old price, markets moved 10% | E2E test with simulated price lag | Timestamp validation, staleness check |
| **Partial trade execution** | 2 of 5 trades succeed, portfolio unbalanced | E2E test with simulated contract failures | Atomic transactions or rollback |
| **Cache returns wrong symbol** | BTC request returns ETH price | Integration test + Unit test | Cache key validation |
| **Unauthorized rebalance** | Attacker triggers rebalance on victim's portfolio | E2E auth test | JWT validation, ownership checks |

---

### 4.2 HIGH Risk Scenarios (Integration Tests Required)

| Scenario | What Could Go Wrong | Test Coverage | Mitigation |
|----------|---------------------|---------------|------------|
| **API rate limiting cascades** | Rate limit causes timeout, retry storm | Integration test with 429 mocking | Exponential backoff, circuit breaker |
| **Database write failures** | Rebalance executes but not recorded | Integration test with DB mocking | Idempotency, retry logic |
| **Concurrent rebalance attempts** | User double-clicks, initiates 2 rebalances | Integration test with race condition | Locking mechanism, idempotency keys |
| **Gas price spike** | Transaction stuck, rebalance pending for hours | Integration test on testnet | Gas price estimation, timeout handling |

---

### 4.3 LOW Risk Scenarios (Unit Tests Sufficient)

| Scenario | What Could Go Wrong | Test Coverage | Mitigation |
|----------|---------------------|---------------|------------|
| **Rounding errors** | $0.01 discrepancies in allocations | Unit tests with edge cases | Precision handling |
| **UI display formatting** | Shows 6 decimal places instead of 2 | Unit test on formatting logic | Standardized formatters |
| **Cache hit performance** | Slow response even with cache | Unit benchmark test | Profiling, optimization |

---

## 5. Quality Gates for CI/CD

### 5.1 Pre-Commit (Local Developer Machine)
```yaml
Checks:
  - Linting (ESLint, Pylint)
  - Type checking (TypeScript, mypy)
  - Unit tests for changed files
  - Code formatting (Prettier, Black)

Pass Criteria:
  - Zero linting errors
  - Zero type errors
  - All unit tests pass

Execution Time: <1 minute
```

---

### 5.2 Pull Request (GitHub Actions)
```yaml
Checks:
  - All unit tests (full suite)
  - Integration tests (API + Price Service)
  - Code coverage report
  - Security scanning (Snyk, Dependabot)

Pass Criteria:
  - 100% of CRITICAL unit tests pass
  - 100% of CRITICAL integration tests pass
  - Code coverage >90% (or no decrease from main)
  - No high/critical security vulnerabilities

Execution Time: 3-5 minutes

Blocking Failures:
  - Any test with "BLOCK PR MERGE" fails
  - Coverage drops below threshold
  - Security vulnerability introduced
```

---

### 5.3 Pre-Deployment (Staging Environment)
```yaml
Checks:
  - All unit tests
  - All integration tests
  - E2E tests (critical paths)
  - Load testing (optional, weekly)
  - Manual QA smoke test

Pass Criteria:
  - 100% of CRITICAL and HIGH tests pass
  - E2E critical paths succeed
  - Manual QA sign-off

Execution Time: 15-30 minutes

Blocking Failures:
  - Any test with "BLOCK DEPLOYMENT" fails
  - E2E test fails on critical path
  - QA identifies critical bug
```

---

## 6. Test Data Strategy

### 6.1 Price Data Fixtures

```json
// tests/fixtures/price_responses.json
{
  "valid_btc": {"name": "BTC", "price": 45000.50},
  "valid_eth": {"name": "ETH", "price": 3000.25},
  "negative_price": {"price": -100},
  "zero_price": {"price": 0},
  "null_price": {"price": null},
  "missing_price": {"name": "BTC", "volume": 1000},
  "rate_limit_response": {
    "status": 429,
    "headers": {"Retry-After": "60"}
  }
}
```

### 6.2 Portfolio Fixtures

```json
// tests/fixtures/portfolios.json
{
  "balanced_portfolio": {
    "BTC": 0.5,
    "ETH": 2.0,
    "SOL": 10.0
  },
  "single_asset": {
    "BTC": 1.0
  },
  "empty_portfolio": {},
  "large_portfolio": {
    // 100 different assets
  }
}
```

### 6.3 Smart Contract Test Scenarios

```solidity
// tests/contracts/RebalanceTest.sol
contract RebalanceTest {
  function test_successfulSwap() { /* ... */ }
  function test_slippageTooHigh() { /* ... */ }
  function test_insufficientBalance() { /* ... */ }
  function test_contractPaused() { /* ... */ }
}
```

---

## 7. Monitoring and Alerting (Post-Deployment)

### 7.1 Real-Time Monitoring

| Metric | Alert Threshold | Severity | Action |
|--------|-----------------|----------|--------|
| Price fetch failure rate | >5% over 5 min | **CRITICAL** | Alert on-call, check API status |
| Cache hit rate drop | <50% (normally 80%) | HIGH | Investigate cache service |
| Rebalance failure rate | >2% over 15 min | **CRITICAL** | Halt auto-rebalances, investigate |
| Average rebalance time | >2 minutes (normally 30s) | MEDIUM | Check price API latency |
| Negative price detected | ANY instance | **CRITICAL** | Halt all trading, security review |

### 7.2 Daily Health Checks

- Run subset of E2E tests against production
- Verify cache TTL is appropriate
- Check for API version changes
- Review error logs for patterns

---

## 8. Regression Testing Strategy

### 8.1 When to Add Regression Tests

**Every production bug becomes a regression test:**
1. Bug discovered in production
2. Write failing test that reproduces bug
3. Fix bug
4. Verify test passes
5. Add test to regression suite (never remove)

### 8.2 Regression Suite Composition

```
Regression Suite =
  All bug-fix tests from past 12 months +
  All CRITICAL path tests +
  High-risk scenario tests from Test Matrix
```

**Execution:** On every deployment (mandatory)

---

## 9. Performance Testing

### 9.1 Load Test Scenarios

| Scenario | Load Profile | Pass Criteria | Failure Impact |
|----------|--------------|---------------|----------------|
| **Concurrent Rebalances** | 100 users rebalance simultaneously | <2s average response time,<br>Zero failures | **BLOCK DEPLOYMENT** |
| **High-Frequency Price Fetches** | 1000 price requests/sec | <100ms p95 latency,<br>Cache hit rate >80% | **MANUAL REVIEW** |
| **Market Flash Crash** | 10,000 users rebalance within 1 minute | System handles gracefully,<br>Queue overflow prevented | **BLOCK DEPLOYMENT** |

**Frequency:** Weekly on staging, before major releases

---

## 10. Example: Full Test Flow for Price-Critical Feature

### Feature: Add support for new crypto symbol (e.g., "ARB")

#### Test Checklist:

**Unit Tests:**
- [ ] `get_hyperliquid_price("ARB")` returns valid price
- [ ] Negative price detection works for ARB
- [ ] Cache stores ARB price correctly
- [ ] Symbol validation allows "ARB"

**Integration Tests:**
- [ ] Fetch ARB + BTC prices concurrently
- [ ] Rebalance calculation includes ARB
- [ ] Database stores ARB holdings

**E2E Tests:**
- [ ] User can add ARB to portfolio via UI
- [ ] Rebalance works with ARB included
- [ ] ARB price displays correctly in UI

**Manual QA:**
- [ ] Test on staging with real Hyperliquid API
- [ ] Verify ARB icon/name renders in UI
- [ ] Check rebalance works with 100% ARB portfolio

**Deployment:**
- [ ] Feature flag: Enable ARB for 10% of users
- [ ] Monitor for 24 hours
- [ ] Gradual rollout to 100%

---

## 11. Continuous Improvement

### 11.1 Monthly Test Review
- Analyze test execution times (remove flaky tests)
- Review test coverage gaps
- Update test matrix based on production incidents

### 11.2 Quarterly Risk Reassessment
- Re-evaluate severity classifications
- Add tests for new attack vectors
- Update E2E scenarios based on user behavior

---

## 12. Conclusion

This test matrix ensures **comprehensive coverage** of the TM100 rebalance process:

✅ **60% Unit Tests** - Fast feedback on core logic
✅ **30% Integration Tests** - API and service interactions
✅ **10% E2E Tests** - Critical user paths
✅ **Quality Gates** - Block bad code at every stage
✅ **Risk-Based** - More tests for high-risk scenarios

**Philosophy:**
- Test the critical paths thoroughly
- Use cheaper tests (unit) when possible
- Reserve expensive tests (E2E) for integration validation
- Never skip CRITICAL tests, even under time pressure

This strategy balances **speed** (fast unit tests) with **confidence** (E2E coverage of critical paths), ensuring user funds are protected while maintaining rapid development velocity.
