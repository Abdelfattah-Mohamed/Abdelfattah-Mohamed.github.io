package com.circuitbreaker;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Lightweight self-contained tests (no JUnit dependency).
 * Run: {@code java com.circuitbreaker.CircuitBreakerTest}
 */
public final class CircuitBreakerTest {

    private static final AtomicInteger passed = new AtomicInteger();
    private static final AtomicInteger failed = new AtomicInteger();

    public static void main(String[] args) throws Exception {
        opensWhenFailuresReachThresholdInWindow();
        staysClosedWhenFailuresAreSpreadBeyondWindow();
        failFastWhileOpen();
        closesAfterCoolOff();
        executeRecordsFailureAndRethrows();
        concurrentFailuresOpenExactlyOnce();

        System.out.printf("%nResults: %d passed, %d failed%n", passed.get(), failed.get());
        if (failed.get() > 0) {
            System.exit(1);
        }
    }

    private static void opensWhenFailuresReachThresholdInWindow() {
        MutableClock clock = new MutableClock(Instant.parse("2026-01-01T00:00:00Z"));
        CircuitBreaker cb = new CircuitBreaker(
                "orders", Duration.ofMinutes(5), 3, Duration.ofMinutes(2), clock);

        cb.recordFailure();
        clock.advance(Duration.ofMinutes(1));
        cb.recordFailure();
        clock.advance(Duration.ofMinutes(1));
        assertEquals(CircuitState.CLOSED, cb.getState(), "still closed after 2 failures");
        cb.recordFailure();
        assertEquals(CircuitState.OPEN, cb.getState(), "opens at threshold Y=3");
    }

    private static void staysClosedWhenFailuresAreSpreadBeyondWindow() {
        MutableClock clock = new MutableClock(Instant.parse("2026-01-01T00:00:00Z"));
        CircuitBreaker cb = new CircuitBreaker(
                "orders", Duration.ofMinutes(5), 3, Duration.ofMinutes(2), clock);

        cb.recordFailure();
        clock.advance(Duration.ofMinutes(6)); // first failure falls out of window
        cb.recordFailure();
        cb.recordFailure();
        assertEquals(CircuitState.CLOSED, cb.getState(), "stale failures must not count");
        assertEquals(2, cb.getCurrentFailureCount(), "only 2 failures in window");
    }

    private static void failFastWhileOpen() {
        MutableClock clock = new MutableClock(Instant.parse("2026-01-01T00:00:00Z"));
        CircuitBreaker cb = new CircuitBreaker(
                "payments", Duration.ofMinutes(5), 2, Duration.ofMinutes(10), clock);

        cb.recordFailure();
        cb.recordFailure();
        assertEquals(CircuitState.OPEN, cb.getState(), "open");

        AtomicInteger invocations = new AtomicInteger();
        try {
            cb.execute(invocations::incrementAndGet);
            fail("expected CircuitOpenException");
        } catch (CircuitOpenException expected) {
            // ok
        }
        assertEquals(0, invocations.get(), "API must not be invoked while OPEN");
        assertFalse(cb.allowRequest(), "allowRequest false while cooling off");
    }

    private static void closesAfterCoolOff() {
        MutableClock clock = new MutableClock(Instant.parse("2026-01-01T00:00:00Z"));
        Duration coolOff = Duration.ofMinutes(3);
        CircuitBreaker cb = new CircuitBreaker(
                "inventory", Duration.ofMinutes(5), 2, coolOff, clock);

        cb.recordFailure();
        cb.recordFailure();
        assertEquals(CircuitState.OPEN, cb.getState(), "open");

        clock.advance(Duration.ofMinutes(2));
        assertEquals(CircuitState.OPEN, cb.getState(), "still open before Z minutes");

        clock.advance(Duration.ofMinutes(1));
        assertEquals(CircuitState.CLOSED, cb.getState(), "closed after cool-off Z");
        assertTrue(cb.allowRequest(), "traffic resumes after cool-off");
    }

    private static void executeRecordsFailureAndRethrows() {
        MutableClock clock = new MutableClock(Instant.parse("2026-01-01T00:00:00Z"));
        CircuitBreaker cb = new CircuitBreaker(
                "catalog", Duration.ofMinutes(5), 5, Duration.ofMinutes(1), clock);

        try {
            cb.execute(() -> {
                throw new IllegalStateException("boom");
            });
            fail("expected IllegalStateException");
        } catch (IllegalStateException expected) {
            // ok
        }
        assertEquals(1, cb.getCurrentFailureCount(), "failure recorded");
        assertEquals(CircuitState.CLOSED, cb.getState(), "below threshold stays closed");
    }

    private static void concurrentFailuresOpenExactlyOnce() throws Exception {
        MutableClock clock = new MutableClock(Instant.parse("2026-01-01T00:00:00Z"));
        int threshold = 50;
        CircuitBreaker cb = new CircuitBreaker(
                "search", Duration.ofMinutes(10), threshold, Duration.ofMinutes(5), clock);

        int threads = 20;
        int failuresPerThread = 5; // 100 total failures
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicReference<Throwable> error = new AtomicReference<>();

        for (int t = 0; t < threads; t++) {
            pool.submit(() -> {
                try {
                    start.await();
                    for (int i = 0; i < failuresPerThread; i++) {
                        cb.recordFailure();
                    }
                } catch (Throwable ex) {
                    error.compareAndSet(null, ex);
                } finally {
                    done.countDown();
                }
            });
        }

        start.countDown();
        assertTrue(done.await(10, TimeUnit.SECONDS), "workers finished");
        pool.shutdownNow();
        if (error.get() != null) {
            throw new AssertionError("worker failed", error.get());
        }
        assertEquals(CircuitState.OPEN, cb.getState(), "circuit opened under concurrent load");
    }

    // --- helpers ---

    private static void assertEquals(Object expected, Object actual, String msg) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            fail(msg + " expected=" + expected + " actual=" + actual);
        } else {
            pass(msg);
        }
    }

    private static void assertTrue(boolean condition, String msg) {
        if (!condition) {
            fail(msg);
        } else {
            pass(msg);
        }
    }

    private static void assertFalse(boolean condition, String msg) {
        assertTrue(!condition, msg);
    }

    private static void pass(String msg) {
        passed.incrementAndGet();
        System.out.println("PASS: " + msg);
    }

    private static void fail(String msg) {
        failed.incrementAndGet();
        System.out.println("FAIL: " + msg);
    }

    /** Controllable clock for deterministic time-window / cool-off tests. */
    static final class MutableClock extends Clock {
        private final AtomicReference<Instant> instant;

        MutableClock(Instant start) {
            this.instant = new AtomicReference<>(start);
        }

        void advance(Duration amount) {
            instant.updateAndGet(i -> i.plus(amount));
        }

        @Override
        public ZoneOffset getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(java.time.ZoneId zone) {
            return Clock.fixed(instant.get(), zone);
        }

        @Override
        public Instant instant() {
            return instant.get();
        }
    }

    private CircuitBreakerTest() {}
}
