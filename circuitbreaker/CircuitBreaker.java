import java.util.LinkedList;
import java.util.Queue;

/**
 * Simple circuit breaker for a pair-programming interview.
 *
 * X = windowMinutes   – count errors only in the last X minutes
 * Y = errorThreshold  – open when error count in that window >= Y
 * Z = coolOffMinutes  – stay open for Z minutes, then close again
 *
 * Thread-safety: all public methods are synchronized.
 */
public class CircuitBreaker {

    enum State { CLOSED, OPEN }

    private final long windowMillis;
    private final int errorThreshold;
    private final long coolOffMillis;

    // timestamps (ms) of recent errors – oldest at the front
    private final Queue<Long> errors = new LinkedList<>();

    private State state = State.CLOSED;
    private long openedAtMillis;

    public CircuitBreaker(int windowMinutes, int errorThreshold, int coolOffMinutes) {
        this.windowMillis = windowMinutes * 60_000L;
        this.errorThreshold = errorThreshold;
        this.coolOffMillis = coolOffMinutes * 60_000L;
    }

    /** Can we call the remote API? Fail-fast if the circuit is open. */
    public synchronized boolean allowRequest() {
        if (state == State.OPEN) {
            if (System.currentTimeMillis() - openedAtMillis >= coolOffMillis) {
                // cool-off over → close the circuit
                state = State.CLOSED;
                errors.clear();
                return true;
            }
            return false; // still cooling off → fail fast
        }
        return true;
    }

    /** Call this when the remote API fails. */
    public synchronized void recordFailure() {
        if (state == State.OPEN) {
            return;
        }

        long now = System.currentTimeMillis();
        errors.add(now);
        removeOldErrors(now);

        if (errors.size() >= errorThreshold) {
            state = State.OPEN;
            openedAtMillis = now;
            errors.clear();
        }
    }

    /** Call this when the remote API succeeds (optional for this problem). */
    public synchronized void recordSuccess() {
        // no-op for CLOSED/OPEN + cool-off model
    }

    public synchronized State getState() {
        allowRequest(); // may close after cool-off
        return state;
    }

    private void removeOldErrors(long now) {
        while (!errors.isEmpty() && now - errors.peek() > windowMillis) {
            errors.poll();
        }
    }

    // --- tiny demo ---
    public static void main(String[] args) {
        // X=5 min, Y=3 errors, Z=2 min
        CircuitBreaker cb = new CircuitBreaker(5, 3, 2);

        for (int i = 1; i <= 5; i++) {
            if (!cb.allowRequest()) {
                System.out.println("call " + i + ": FAIL FAST (circuit OPEN)");
                continue;
            }
            // pretend API failed
            cb.recordFailure();
            System.out.println("call " + i + ": API error recorded, state=" + cb.getState());
        }
    }
}
