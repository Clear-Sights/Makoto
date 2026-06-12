#!/bin/sh
# Bash test assertion helpers.

PASS_COUNT=0
FAIL_COUNT=0

assert_eq() {
  local expected="$1"
  local actual="$2"
  local msg="$3"
  if [ "$expected" = "$actual" ]; then
    PASS_COUNT=$((PASS_COUNT + 1))
    printf "  PASS: %s\n" "$msg"
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf "  FAIL: %s\n    expected: %s\n    actual:   %s\n" "$msg" "$expected" "$actual"
  fi
}

assert_exit_code() {
  local expected="$1"
  local actual="$2"
  local msg="$3"
  if [ "$expected" = "$actual" ]; then
    PASS_COUNT=$((PASS_COUNT + 1))
    printf "  PASS: %s (exit %s)\n" "$msg" "$actual"
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf "  FAIL: %s (expected exit %s, got %s)\n" "$msg" "$expected" "$actual"
  fi
}

assert_file_exists() {
  local path="$1"
  local msg="$2"
  if [ -f "$path" ]; then
    PASS_COUNT=$((PASS_COUNT + 1))
    printf "  PASS: %s\n" "$msg"
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf "  FAIL: %s (no file at %s)\n" "$msg" "$path"
  fi
}

test_summary() {
  printf "\nTOTAL: %d passed, %d failed\n" "$PASS_COUNT" "$FAIL_COUNT"
  [ "$FAIL_COUNT" -eq 0 ]
}
