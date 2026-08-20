# Circuit Breaker (interview — 1 class)

Single file: `CircuitBreaker.java`

| | Meaning |
|-|---------|
| **X** | window minutes |
| **Y** | open when errors in window ≥ Y |
| **Z** | cool-off minutes before closing again |

```bash
javac CircuitBreaker.java && java CircuitBreaker
```

Thread-safety: `synchronized` on every public method.
