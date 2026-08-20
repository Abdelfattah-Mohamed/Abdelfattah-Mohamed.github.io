package com.circuitbreaker.demo;

import com.circuitbreaker.CircuitBreaker;
import com.circuitbreaker.CircuitBreakerRegistry;
import com.circuitbreaker.CircuitOpenException;
import com.circuitbreaker.CircuitState;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Small console demo of the circuit breaker requirements:
 * <ul>
 *   <li>X = 1 minute window</li>
 *   <li>Y = 3 failures open the circuit</li>
 *   <li>Z = cool-off simulated by constructing a breaker with a short cool-off in tests;
 *       here we just show fail-fast when open.</li>
 * </ul>
 */
public final class Demo {

    public static void main(String[] args) {
        // X=1 min, Y=3 errors, Z=2 min (typical interview knobs)
        CircuitBreakerRegistry registry = new CircuitBreakerRegistry(
                Duration.ofMinutes(1),
                3,
                Duration.ofMinutes(2));

        CircuitBreaker paymentApi = registry.forService("payment-service");
        AtomicInteger attempts = new AtomicInteger();

        System.out.println("=== Recording failures until circuit opens ===");
        for (int i = 1; i <= 5; i++) {
            try {
                paymentApi.execute(() -> {
                    attempts.incrementAndGet();
                    throw new RuntimeException("upstream 500");
                });
            } catch (CircuitOpenException open) {
                System.out.printf("call %d: FAIL-FAST (%s), state=%s%n",
                        i, open.getMessage(), paymentApi.getState());
            } catch (RuntimeException ex) {
                System.out.printf("call %d: upstream failed (%s), state=%s, windowFailures=%d%n",
                        i, ex.getMessage(), paymentApi.getState(), paymentApi.getCurrentFailureCount());
            }
        }

        System.out.println();
        System.out.println("Attempts that reached the remote API: " + attempts.get());
        System.out.println("Final state: " + paymentApi.getState());
        System.out.println("Expected: OPEN after 3 failures; subsequent calls fail-fast without invoking the API.");
        assert paymentApi.getState() == CircuitState.OPEN;
    }

    private Demo() {}
}
