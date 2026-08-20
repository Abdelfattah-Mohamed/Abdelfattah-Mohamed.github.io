#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/out"
rm -rf "$OUT"
mkdir -p "$OUT"

echo "Compiling main sources..."
find "$ROOT/src/main/java" -name '*.java' > "$OUT/sources.txt"
javac -d "$OUT" @"$OUT/sources.txt"

echo "Compiling tests..."
find "$ROOT/src/test/java" -name '*.java' > "$OUT/test-sources.txt"
javac -cp "$OUT" -d "$OUT" @"$OUT/test-sources.txt"

echo "Running tests..."
java -cp "$OUT" com.circuitbreaker.CircuitBreakerTest

echo "Running demo..."
java -cp "$OUT" com.circuitbreaker.demo.Demo

echo "OK"
