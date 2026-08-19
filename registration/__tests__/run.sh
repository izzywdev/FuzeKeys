#!/usr/bin/env bash
# Regression tests for registration/register.sh.
#
# WHY THIS EXISTS: register.sh runs in an INIT CONTAINER whose image is
# curlimages/curl:8.8.0 — busybox + sh + curl, and nothing else. It has no jq.
# A previous version of this script opened with `command -v jq || die`, so the
# container died at preflight, BEFORE it ever contacted the registry, and the pod
# CrashLoopBackOff'd with a failure indistinguishable from a bad token: identical
# pod state, completely different cause. Nothing in CI caught it, because nothing
# in CI ran this script.
#
# Test 1 is the one that would have caught it. It runs register.sh on a PATH that
# contains ONLY what the real image contains, so "works on my machine" — where jq
# happens to be installed — cannot mask a reintroduced dependency.
#
# Usage: bash registration/__tests__/run.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REG="$(dirname "$HERE")"
SCRIPT="$REG/register.sh"
SLUG="$(tr -d '\n' < "$REG/manifest.json" \
        | grep -o '"slug"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 \
        | sed 's/.*:[[:space:]]*"//; s/"$//')"
[ -n "$SLUG" ] || { echo "FAIL: could not read .slug from $REG/manifest.json"; exit 1; }

fail=0
pass() { echo "  PASS  $1"; }
bad()  { echo "  FAIL  $1"; fail=1; }

# --- 1. no jq, and nothing else outside the image's toolset -------------------
# The image's entire userland: bin/busybox, bin/sh, usr/bin/curl. Everything
# below except curl is a busybox applet.
BIN="$(mktemp -d)"
for b in sh curl tr grep sed head mktemp cat sleep rm dirname; do
  p="$(command -v "$b")" && ln -sf "$p" "$BIN/$b"
done
command -v jq >/dev/null 2>&1 && echo "  (note: jq IS installed here; test 1 hides it deliberately)"

PORT=18831
for scenario in fresh existing-inactive existing-active bad-token; do
  PORT=$((PORT + 1))
  LOGFILE="$(mktemp)"
  SCENARIO="$scenario" SLUG="$SLUG" LOGFILE="$LOGFILE" \
    python3 "$HERE/mock_registry.py" "$PORT" &
  srv=$!
  ready=0
  for _ in $(seq 1 60); do
    curl -s -o /dev/null "http://127.0.0.1:$PORT/" && { ready=1; break; }
    sleep 0.1
  done
  [ "$ready" = 1 ] || { bad "$scenario: mock registry never came up"; kill $srv 2>/dev/null; continue; }

  token=good-token
  [ "$scenario" = bad-token ] && token=bad-token

  out="$(env -i PATH="$BIN" \
          REGISTRATION_DIR="$REG" \
          FUZEFRONT_API_URL="http://127.0.0.1:$PORT" \
          FUZEFRONT_REGISTRATION_TOKEN="$token" \
          "$BIN/sh" "$SCRIPT" 2>&1)"
  rc=$?
  kill -TERM $srv 2>/dev/null; wait $srv 2>/dev/null

  # bad-token MUST fail: registration is fail-closed on purpose — an unregistered
  # app cannot do AuthN/AuthZ/billing, so the pod must not start.
  want=0; [ "$scenario" = bad-token ] && want=1
  if [ "$rc" = "$want" ]; then
    pass "$scenario exits $want on an image with no jq"
  else
    bad "$scenario exited $rc, wanted $want"
    echo "$out" | sed 's/^/        /'
  fi
  rm -f "$LOGFILE"
done
rm -rf "$BIN"

# --- 2. the POST body is the manifest, wrapped, and still valid JSON ----------
# The mock parses it strictly and asserts manifest.slug round-trips, so a broken
# hand-built body fails test 1's `fresh` case rather than passing silently.
grep -q 'printf .{"manifest":%s}' "$SCRIPT" \
  && pass "POST body is built with printf, not a JSON tool" \
  || bad  "POST body construction changed — re-check it round-trips"

# --- 3. no jq invocation survives anywhere in the script ---------------------
# Belt and braces with test 1: this one names the defect, so a reviewer who
# reintroduces `jq` sees WHY it fails instead of only THAT it fails.
if grep -v '^[[:space:]]*#' "$SCRIPT" | grep -qE '(^|[|&;(`]|\$\()[[:space:]]*jq[[:space:]]'; then
  bad "register.sh invokes jq — the init image (curlimages/curl) does not have it"
else
  pass "register.sh invokes jq nowhere"
fi

# --- 4. the response parser tolerates a space after the colon ----------------
# Recorded bug: a parser requiring `"status":"x"` read `"status": "x"` as empty
# and silently took the wrong branch. The mock serves the pretty-printed form.
resp="$(mktemp)"; printf '{\n  "slug": "x",\n  "status": "activated"\n}' > "$resp"
got="$(tr -d '\n' < "$resp" | grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' \
       | head -1 | sed 's/.*:[[:space:]]*"//; s/"$//')"
rm -f "$resp"
[ "$got" = activated ] \
  && pass "status parses from a pretty-printed response" \
  || bad  "status parsed as '$got', wanted 'activated'"

echo
[ "$fail" = 0 ] && echo "registration tests: all passed" || echo "registration tests: FAILURES"
exit $fail
