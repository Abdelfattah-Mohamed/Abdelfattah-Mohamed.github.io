package com.circuitbreaker;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Objects;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.Supplier;

/**
 * Thread-safe circuit breaker for service-to-service API calls.
 *
 * <h2>Behavior</h2>
 * <ol>
 *   <li>While {@link CircuitState#CLOSED}, requests are allowed. Each failure is recorded
 *       with a timestamp. If the number of failures in the last {@code windowDuration}
 *       reaches {@code failureThreshold}, the circuit opens.</li>
 *   <li>While {@link CircuitState#OPEN}, calls fail fast with {@link CircuitOpenException}.
 *       After {@code coolOffDuration} has elapsed since opening, the circuit closes again
 *       and starts accepting traffic.</li>
 * </ol>
 *
 * <h2>Thread safety</h2>
 * All mutable state (sliding window of failure timestamps, circuit state, open timestamp)
 * is guarded by a {@link ReentrantLock}. Call sites never need external synchronization.
 * A {@link Clock} can be injected for deterministic tests.
 *
 * @param windowDuration   X – sliding window used to count recent failures
 * @param failureThreshold Y – open the circuit when failure count in the window reaches this
 * @param coolOffDuration  Z – keep the circuit open at least this long before closing again
 */
public final class CircuitBreaker {

    private final String serviceName;
    private final Duration windowDuration;
    private final int failureThreshold;
    private final Duration coolOffDuration;
    private final Clock clock;

    /** Guard for {@link #failureTimestamps}, {@link #state}, and {@link #openedAt}. */
    private final ReentrantLock lock = new ReentrantLock();

    /** Failure timestamps inside the current sliding window (oldest at the head). */
    private final Deque<Instant> failureTimestamps = new ArrayDeque<>();

    private CircuitState state = CircuitState.CLOSED;
    private Instant openedAt;

    public CircuitBreaker(
            String serviceName,
            Duration windowDuration,
            int failureThreshold,
            Duration coolOffDuration) {
        this(serviceName, windowDuration, failureThreshold, coolOffDuration, Clock.systemUTC());
    }

    public CircuitBreaker(
            String serviceName,
            Duration windowDuration,
            int failureThreshold,
            Duration coolOffDuration,
            Clock clock) {
        if (windowDuration == null || windowDuration.isNegative() || windowDuration.isZero()) {
            throw new IllegalArgumentException("windowDuration (X) must be positive");
        }
        if (failureThreshold < 1) {
            throw new IllegalArgumentException("failureThreshold (Y) must be >= 1");
        }
        if (coolOffDuration == null || coolOffDuration.isNegative() || coolOffDuration.isZero()) {
            throw new IllegalArgumentException("coolOffDuration (Z) must be positive");
        }
        this.serviceName = Objects.requireNonNull(serviceName, "serviceName");
        this.windowDuration = windowDuration;
        this.failureThreshold = failureThreshold;
        this.coolOffDuration = coolOffDuration;
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    /**
     * Returns {@code true} if a request may proceed; {@code false} if the circuit is open
     * and still within the cool-off period. Transition from OPEN → CLOSED happens here when
     * cool-off has elapsed (lazy recovery).
     */
    public boolean allowRequest() {
        lock.lock();
        try {
            maybeCloseAfterCoolOff();
            return state == CircuitState.CLOSED;
        } finally {
            lock.unlock();
        }
    }

    /**
     * Executes {@code action} only if the circuit is closed; otherwise fails fast.
     * On success the call is a no-op for the breaker; on failure {@link #recordFailure()}
     * is invoked.
     */
    public <T> T execute(Supplier<T> action) {
        if (!allowRequest()) {
            throw new CircuitOpenException(serviceName);
        }
        try {
            return action.get();
        } catch (RuntimeException ex) {
            recordFailure();
            throw ex;
        }
    }

    public void execute(Runnable action) {
        execute(() -> {
            action.run();
            return null;
        });
    }

    /**
     * Records a failed API call. Prunes timestamps older than the window, then opens the
     * circuit if the remaining count is {@code >= failureThreshold}.
     */
    public void recordFailure() {
        lock.lock();
        try {
            maybeCloseAfterCoolOff();
            // Failures while already OPEN do not extend cool-off or re-open; cool-off
            // is measured from the first time we transitioned to OPEN.
            if (state == CircuitState.OPEN) {
                return;
            }

            Instant now = clock.instant();
            failureTimestamps.addLast(now);
            pruneStaleFailures(now);

            if (failureTimestamps.size() >= failureThreshold) {
                state = CircuitState.OPEN;
                openedAt = now;
                failureTimestamps.clear();
            }
        } finally {
            lock.unlock();
        }
    }

    /** Optional: record a successful call (no effect on state under these requirements). */
    public void recordSuccess() {
        // Intentionally empty for the stated CLOSED/OPEN + cool-off model.
        // Kept so callers can wire success paths symmetrically.
    }

    public CircuitState getState() {
        lock.lock();
        try {
            maybeCloseAfterCoolOff();
            return state;
        } finally {
            lock.unlock();
        }
    }

    public String getServiceName() {
        return serviceName;
    }

    /** Visible for tests / diagnostics. */
    public int getCurrentFailureCount() {
        lock.lock();
        try {
            pruneStaleFailures(clock.instant());
            return failureTimestamps.size();
        } finally {
            lock.unlock();
        }
    }

    private void maybeCloseAfterCoolOff() {
        if (state != CircuitState.OPEN || openedAt == null) {
            return;
        }
        Instant now = clock.instant();
        if (!now.isBefore(openedAt.plus(coolOffDuration))) {
            state = CircuitState.CLOSED;
            openedAt = null;
            failureTimestamps.clear();
        }
    }

    private void pruneStaleFailures(Instant now) {
        Instant cutoff = now.minus(windowDuration);
        while (!failureTimestamps.isEmpty() && failureTimestamps.peekFirst().isBefore(cutoff)) {
            failureTimestamps.removeFirst();
        }
    }
}
