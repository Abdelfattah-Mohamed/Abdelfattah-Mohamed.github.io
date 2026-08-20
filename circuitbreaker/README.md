# Circuit Breaker (Java)

Thread-safe circuit breaker for service-to-service API calls, matching a common HackerRank / pair-programming prompt.

## Requirements covered

| Knob | Meaning |
|------|---------|
| **X** | Sliding time window (e.g. last X minutes) |
| **Y** | Open the circuit when failure count in that window `>= Y` |
| **Z** | Cool-off period: stay OPEN for Z minutes, then close and accept traffic again |

1. **Open + fail-fast** – if failures in the last X minutes reach Y, the circuit opens and subsequent calls throw `CircuitOpenException` without calling the remote API.
2. **Cool-off close** – after Z minutes in OPEN, the circuit closes (lazy check on the next `allowRequest` / `getState` / `recordFailure`).
3. **Thread-safe** – all mutable state is guarded by a `ReentrantLock`; the registry uses `ConcurrentHashMap`.

## States

```
CLOSED --(Y failures in last X minutes)--> OPEN
OPEN   --(Z minutes elapsed)-------------> CLOSED
```

There is no HALF_OPEN in this version (not required by the prompt). You can extend `maybeCloseAfterCoolOff` to allow a single probe request if interviewers ask.

## Quick start

```bash
cd circuitbreaker
chmod +x build-and-test.sh
./build-and-test.sh
```

Requires JDK 11+ (tested with 21).

## Usage

```java
CircuitBreakerRegistry registry = new CircuitBreakerRegistry(
        Duration.ofMinutes(5),  // X
        10,                     // Y
        Duration.ofMinutes(2)); // Z

CircuitBreaker breaker = registry.forService("payment-service");

String result = breaker.execute(() -> httpClient.get("/pay"));
```

Or manually:

```java
if (!breaker.allowRequest()) {
    throw new CircuitOpenException("payment-service");
}
try {
    callRemote();
    breaker.recordSuccess();
} catch (Exception e) {
    breaker.recordFailure();
    throw e;
}
```

## Thread-safety design

- **Single lock** (`ReentrantLock`) around the sliding window (`Deque<Instant>`), `state`, and `openedAt`.
- **Why not only atomics?** Opening the circuit needs a check-then-act on “count ≥ Y” plus clearing the window and setting `openedAt`. A lock keeps that atomic and easy to reason about in an interview.
- **Registry** creates at most one breaker per service name via `computeIfAbsent`.
- **Clock injection** enables deterministic unit tests without `Thread.sleep`.

## Project layout

```
circuitbreaker/
  src/main/java/com/circuitbreaker/
    CircuitBreaker.java
    CircuitBreakerRegistry.java
    CircuitOpenException.java
    CircuitState.java
    demo/Demo.java
  src/test/java/com/circuitbreaker/
    CircuitBreakerTest.java
  build-and-test.sh
```
