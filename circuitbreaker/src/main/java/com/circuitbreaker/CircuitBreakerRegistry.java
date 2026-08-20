package com.circuitbreaker;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Registry of per-remote-service circuit breakers for a multi-service network.
 * Thread-safe: each service gets one breaker created at most once via
 * {@link ConcurrentHashMap#computeIfAbsent}.
 */
public final class CircuitBreakerRegistry {

    private final Duration windowDuration;
    private final int failureThreshold;
    private final Duration coolOffDuration;
    private final Map<String, CircuitBreaker> breakers = new ConcurrentHashMap<>();

    public CircuitBreakerRegistry(
            Duration windowDuration,
            int failureThreshold,
            Duration coolOffDuration) {
        this.windowDuration = windowDuration;
        this.failureThreshold = failureThreshold;
        this.coolOffDuration = coolOffDuration;
    }

    public CircuitBreaker forService(String serviceName) {
        return breakers.computeIfAbsent(
                serviceName,
                name -> new CircuitBreaker(name, windowDuration, failureThreshold, coolOffDuration));
    }
}
