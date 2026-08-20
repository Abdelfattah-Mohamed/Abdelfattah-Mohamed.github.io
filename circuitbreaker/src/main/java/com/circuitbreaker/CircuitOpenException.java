package com.circuitbreaker;

/**
 * Thrown when a call is rejected because the circuit is open (fail-fast).
 */
public class CircuitOpenException extends RuntimeException {

    public CircuitOpenException(String serviceName) {
        super("Circuit is OPEN for service '" + serviceName + "'; failing fast");
    }
}
