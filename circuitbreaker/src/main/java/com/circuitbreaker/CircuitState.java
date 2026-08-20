package com.circuitbreaker;

/**
 * Lifecycle states for the circuit breaker.
 *
 * <ul>
 *   <li>{@link #CLOSED} – traffic is allowed; failures are counted in the sliding window.</li>
 *   <li>{@link #OPEN} – traffic is rejected (fail-fast) until the cool-off period elapses.</li>
 * </ul>
 */
public enum CircuitState {
    CLOSED,
    OPEN
}
