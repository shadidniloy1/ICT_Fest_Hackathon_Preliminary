Every fix is minimal, preserves the API contract exactly (paths, status codes, error `code` values, JSON field names, JWT claims), lives on its own `fix/bug-N-*` branch cut from `main`, and passed a targeted self-test.

---

## Summary table

| # | File(s) | Rule | Branch | Commit | Test |
|---|---------|------|--------|--------|------|
| 1 | `app/auth.py` | 8 | `fix/bug-1-access-token-ttl` | 2c27e34 | PASS |
| 2 | `app/auth.py` | 8 | `fix/bug-2-logout-jti` | be2b9d4 | PASS |
| 3 | `app/timeutils.py` | 1 | `fix/bug-3-tz-utc` | 30436dc | PASS |
| 4 | `app/routers/auth.py` | 15 | `fix/bug-4-username-taken` | 8abcc7d | PASS |
| 5 | `app/routers/bookings.py` | 3 | `fix/bug-5-overlap-strict` | 6a00a9d | PASS |
| 6 | `app/routers/bookings.py` | 2 | `fix/bug-6-no-grace` | dfb06fe | PASS |
| 7 | `app/routers/bookings.py` | 11 | `fix/bug-7-pagination` | e8963ee | PASS |
| 8 | `app/routers/bookings.py` | contract | `fix/bug-8-start-time` | c2d3498 | PASS |
| 9 | `app/routers/bookings.py` | 6 | `fix/bug-9-refund-tiers` | f140a7b | PASS |
| 10 | `app/services/notifications.py` | 16 | `fix/bug-10-deadlock` | f0d4352 | PASS |
| 11 | `app/services/reference.py` | 7 | `fix/bug-11-ref-race` | ecb85a7 | PASS |
| 12 | `app/routers/bookings.py` | 2 | `fix/bug-12-min-duration` | 6fdf203 | PASS |
| 13 | `app/services/refunds.py` + `app/routers/bookings.py` | 6 | `fix/bug-13-refund-rounding` | 369a5c2 | PASS |
| 14 | `app/auth.py` + `app/routers/auth.py` | 8 | `fix/bug-14-refresh-single-use` | 7c4e2c5 | PASS |
| 15 | `app/routers/bookings.py` | 10 | `fix/bug-15-booking-idor` | 9863bb2 | PASS |
| 16 | `app/routers/bookings.py` | 13 | `fix/bug-16-cancel-avail-cache` | fe44797 | PASS |
| 17 | `app/services/stats.py` | 14 | `fix/bug-17-stats-race` | 95d8138 | PASS |
| 17b | `app/services/stats.py` | 14 | `fix/bug-17b-revenue-floor` | babbdc5 | PASS |
| 18 | `app/services/export.py` | 9 | `fix/bug-18-export-org-scope` | caca958 | PASS |
| 19 | `app/services/ratelimit.py` | 5 | `fix/bug-19-ratelimit-race` | 2026788 | PASS |
| 20 | `app/routers/bookings.py` | 12 | `fix/bug-20-create-report-cache` | dc190b0 | PASS |
| 21 | `app/routers/auth.py` | 15 | `fix/bug-21-register-race` | f261fd8 | PASS |

Merge state at compilation: #1–#20 and #17b merged into `origin/main` (`1a4461a`); #21 pushed, awaiting merge.

---

## FIX #1 — Access token lifetime 60× too long
**File:** `app/auth.py` · **Function:** `create_access_token` · **Line(s):** ~50
**Bug:** Lifetime computed as `minutes=ACCESS_TOKEN_EXPIRE_MINUTES * 60`, producing a 54,000s (15h) token.
**Why:** Rule 8 requires `exp − iat` to equal exactly 900s; the token stayed valid ~60× longer than allowed.
**Fix:**
```python
# Before
lifetime = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES * 60)
# After
lifetime = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
```
**Branch:** `fix/bug-1-access-token-ttl` (2c27e34)
**Test:** PASS — decoded a fresh access token; `exp − iat == 900`.

---

## FIX #2 — Logout revocation checks the wrong JWT claim
**File:** `app/auth.py` · **Function:** `get_token_payload` · **Line(s):** ~97
**Bug:** Logout stored the token's `jti` in `_revoked_tokens`, but the guard checked `payload.get("sub")` (user id), which never matches a `jti`.
**Why:** Rule 8 requires logout to immediately invalidate the presented access token; the mismatch made logout a no-op.
**Fix:**
```python
# Before
if payload.get("sub") in _revoked_tokens:
# After
if payload.get("jti") in _revoked_tokens:
```
**Branch:** `fix/bug-2-logout-jti` (be2b9d4)
**Test:** PASS — login → authed call 200 → logout → same token → 401.

---

## FIX #3 — Timezone offset stripped, not converted to UTC
**File:** `app/timeutils.py` · **Function:** `parse_input_datetime` · **Line(s):** ~12–13
**Bug:** For offset-aware input, `dt.replace(tzinfo=None)` discarded the offset while keeping the original wall-clock number instead of converting the instant to UTC.
**Why:** Rule 1 requires offset-carrying input to be converted to UTC before storage/comparison; every downstream check (conflict, quota, availability, report) was shifted.
**Fix:**
```python
# Before
if dt.tzinfo is not None:
    dt = dt.replace(tzinfo=None)
# After
if dt.tzinfo is not None:
    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
```
**Branch:** `fix/bug-3-tz-utc` (30436dc)
**Test:** PASS — `parse_input_datetime("2026-07-10T18:00:00+05:00")` → `2026-07-10 13:00:00`.

---

## FIX #4 — Duplicate username returns success instead of 409
**File:** `app/routers/auth.py` · **Function:** `register` · **Line(s):** ~37–43
**Bug:** When `(org_id, username)` already existed, the endpoint returned the existing user's data (HTTP 201) instead of raising a conflict; the submitted password was never checked.
**Why:** Rule 15 requires a duplicate username within an org to return `409 USERNAME_TAKEN`.
**Fix:**
```python
# Before
if existing is not None:
    return {"user_id": existing.id, "org_id": org.id,
            "username": existing.username, "role": existing.role}
# After
if existing is not None:
    raise AppError(409, "USERNAME_TAKEN", "Username already taken in this organization")
```
**Branch:** `fix/bug-4-username-taken` (8abcc7d)
**Test:** PASS — register duplicate `(org, "dave")` → `409 USERNAME_TAKEN`.

---

## FIX #5 — Back-to-back bookings falsely flagged as conflicts
**File:** `app/routers/bookings.py` · **Function:** `_has_conflict` · **Line(s):** ~50
**Bug:** Overlap check used inclusive `<=` on both bounds, so a new booking starting exactly when an existing one ends was treated as overlapping.
**Why:** Rule 3 defines overlap with strict inequality (`existing.start < new.end AND new.start < existing.end`); back-to-back bookings must be allowed.
**Fix:**
```python
# Before
if b.start_time <= end and start <= b.end_time:
# After
if b.start_time < end and start < b.end_time:
```
**Branch:** `fix/bug-5-overlap-strict` (6a00a9d)
**Test:** PASS — book 09:00–10:00, then 10:00–11:00 same room → both 201.

---

## FIX #6 — 5-minute grace window on start_time
**File:** `app/routers/bookings.py` · **Function:** `create_booking` · **Line(s):** ~86
**Bug:** The past-start guard was `start <= now - timedelta(seconds=300)`, allowing a start time up to 5 minutes in the past.
**Why:** Rule 2 requires `start_time` to be strictly in the future with no grace window.
**Fix:**
```python
# Before
if start <= now - timedelta(seconds=300):
# After
if start <= now:
```
**Branch:** `fix/bug-6-no-grace` (dfb06fe)
**Test:** PASS — POST booking with `start_time` = now − 4 min → `400 INVALID_BOOKING_WINDOW`.

---

## FIX #7 — list_bookings: wrong sort, wrong offset, ignored limit
**File:** `app/routers/bookings.py` · **Function:** `list_bookings` · **Line(s):** ~137–140
**Bug:** Three defects in one query — descending sort, `offset(page * limit)` (page 1 skips the first page), and a hardcoded `.limit(10)` that ignored the `limit` parameter.
**Why:** Rule 11 requires ascending `start_time` (ties by ascending `id`), offset `(page − 1) * limit`, and honoring the `limit` parameter with no skipped/repeated items.
**Fix:**
```python
# Before
base.order_by(Booking.start_time.desc(), Booking.id.asc()).offset(page * limit).limit(10)
# After
base.order_by(Booking.start_time.asc(), Booking.id.asc()).offset((page - 1) * limit).limit(limit)
```
**Branch:** `fix/bug-7-pagination` (e8963ee)
**Test:** PASS — 3 bookings created out of order → returned ascending; `?page=1&limit=2` → 2 items, `?page=2&limit=2` → 1 item.

---

## FIX #8 — get_booking overwrites start_time with created_at
**File:** `app/routers/bookings.py` · **Function:** `get_booking` · **Line(s):** ~166
**Bug:** After correctly serializing the booking, the response's `start_time` was overwritten with `created_at`.
**Why:** `start_time` must reflect the booked slot and stay consistent with `POST /bookings` and `GET /bookings` for the same booking.
**Fix:**
```python
# Before
response = serialize_booking(booking)
response["start_time"] = iso_utc(booking.created_at)
# After  (overwrite line deleted)
response = serialize_booking(booking)
```
**Branch:** `fix/bug-8-start-time` (c2d3498)
**Test:** PASS — `GET /bookings/{id}` → `start_time` equals the submitted slot.

---

## FIX #9 — Refund percentage wrong at <24h and exactly-48h boundaries
**File:** `app/routers/bookings.py` · **Function:** `cancel_booking` · **Line(s):** ~201–206
**Bug:** Two defects — `notice_hours > 48` (floored integer, strict `>`) sent exactly-48h notice to the 50% tier, and the `else` branch returned 50% for `<24h` instead of 0%.
**Why:** Rule 6 tiers are ≥48h → 100%, 24–48h → 50%, <24h → 0%.
**Fix:**
```python
# Before
notice_hours = int(notice.total_seconds() // 3600)
if notice_hours > 48:               refund_percent = 100
elif notice >= timedelta(hours=24): refund_percent = 50
else:                               refund_percent = 50
# After
if notice >= timedelta(hours=48):   refund_percent = 100
elif notice >= timedelta(hours=24): refund_percent = 50
else:                               refund_percent = 0
```
**Branch:** `fix/bug-9-refund-tiers` (f140a7b)
**Test:** PASS — ≥48h notice → 100%; <24h notice → 0%.

---

## FIX #10 — AB-BA lock deadlock between create and cancel notifications
**File:** `app/services/notifications.py` · **Function:** `notify_created` + `notify_cancelled` · **Line(s):** ~31–36
**Bug:** `notify_created` acquires `_email_lock` then `_audit_lock`; `notify_cancelled` acquired them in the opposite order (`_audit_lock` then `_email_lock`) — an AB-BA lock ordering that deadlocks under concurrent create+cancel.
**Why:** Rule 16 — the service must never hang under any combination of concurrent valid requests.
**Fix:**
```python
# Before
def notify_cancelled(booking) -> None:
    with _audit_lock:
        _write_audit("cancelled", booking)
        with _email_lock:
            _send_email("cancelled", booking)
# After
def notify_cancelled(booking) -> None:
    with _email_lock:
        with _audit_lock:
            _write_audit("cancelled", booking)
        _send_email("cancelled", booking)
```
Note: explicit restructure (not a naive with-line swap, which would leave `_write_audit` no longer guarded by `_audit_lock`). Both functions now acquire `_email_lock` before `_audit_lock`; each operation stays under its correct lock.
**Branch:** `fix/bug-10-deadlock` (f0d4352)
**Test:** PASS — concurrent create+cancel harness: buggy main deadlocked (stuck >6s); after fix both workers complete. pytest smoke 1 passed.

---

## FIX #11 — Reference code race condition (duplicate codes)
**File:** `app/services/reference.py` · **Function:** `next_reference_code` · **Line(s):** ~19–25
**Bug:** The read-increment-write of `_counter["value"]` is split by `_format_pause()` with no lock, so concurrent callers read the same value and emit duplicate reference codes.
**Why:** Rule 7 — every reference code must be unique, including under concurrent creation.
**Fix:**
```python
# Before
_counter = {"value": 1000}
def next_reference_code() -> str:
    current = _counter["value"]
    _format_pause()
    _counter["value"] = current + 1
    return f"CW-{current:06d}"
# After
import threading
_counter = {"value": 1000}
_counter_lock = threading.Lock()
def next_reference_code() -> str:
    with _counter_lock:
        current = _counter["value"]
        _format_pause()
        _counter["value"] = current + 1
        return f"CW-{current:06d}"
```
**Branch:** `fix/bug-11-ref-race` (ecb85a7)
**Test:** PASS — 12 concurrent calls: buggy main returned 12× CW-001000 (1 distinct); after fix 12 distinct codes CW-001000..CW-001011. pytest smoke 1 passed.

---

## FIX #12 — Missing minimum-duration check (0 / negative duration)
**File:** `app/routers/bookings.py` · **Function:** `create_booking` · **Line(s):** ~89–94
**Bug:** Duration was validated for being whole and not exceeding `MAX_DURATION_HOURS`, but never against `MIN_DURATION_HOURS`, so a 0-hour (`end == start`) or negative-duration booking passed.
**Why:** Rule 2 requires a minimum of 1 hour and `end_time` strictly after `start_time`.
**Fix:**
```python
# Before
if duration_hours > MAX_DURATION_HOURS:
# After
if duration_hours < MIN_DURATION_HOURS or duration_hours > MAX_DURATION_HOURS:
```
**Branch:** `fix/bug-12-min-duration` (6fdf203)
**Test:** PASS — POST with `start_time == end_time` → `400 INVALID_BOOKING_WINDOW`.

---

## FIX #13 — Refund amount mismatch: response (round) vs RefundLog (truncate)
**File:** `app/services/refunds.py` (`log_refund`) + `app/routers/bookings.py` (`cancel_booking`) · **Line(s):** ~15–17 / ~208
**Bug:** `cancel_booking` used Python `round()` (banker's rounding) while `log_refund` truncated via `int()`, so the two could disagree — and neither implemented half-cents-up.
**Why:** Rule 6 requires half-cents rounded up and the cancel-response amount to equal the stored RefundLog amount.
**Fix:**
```python
# refunds.py — After (single half-up computation in integer cents)
import math
amount_cents = math.floor(booking.price_cents * percent / 100 + 0.5)
# bookings.py — After (router reuses the stored value, cannot diverge)
refund_entry = log_refund(db, booking, refund_percent)
refund_amount_cents = refund_entry.amount_cents
```
**Branch:** `fix/bug-13-refund-rounding` (369a5c2)
**Test:** PASS — price 333 at 50% → cancel response and `refunds[0].amount_cents` both equal 167.

---

## FIX #14 — Refresh tokens reusable (not single-use)
**File:** `app/auth.py` + `app/routers/auth.py` · **Function:** `refresh` · **Line(s):** ~81–93
**Bug:** The presented refresh token was decoded and validated but never invalidated, so it could be replayed indefinitely to mint new token pairs.
**Why:** Rule 8 requires refresh tokens to be single-use — a refresh must invalidate the presented token, and reuse must return 401.
**Fix:**
```python
# auth.py — After (new revocation store + helpers)
_used_refresh_jtis: set[str] = set()
def revoke_refresh_token(payload): _used_refresh_jtis.add(payload["jti"])
def is_refresh_token_used(payload): return payload.get("jti") in _used_refresh_jtis
# routers/auth.py refresh() — After
if is_refresh_token_used(data):
    raise AppError(401, "UNAUTHORIZED", "Refresh token already used")
...
revoke_refresh_token(data)   # before minting the new pair
```
**Branch:** `fix/bug-14-refresh-single-use` (7c4e2c5)
**Test:** PASS — login → refresh once (200) → reuse same refresh token → 401.

---

## FIX #15 — get_booking missing member-ownership check (IDOR)
**File:** `app/routers/bookings.py` · **Function:** `get_booking` · **Line(s):** ~150–163
**Bug:** The query scoped only by org, with no check that a non-admin caller owned the booking (the guard existed in `cancel_booking` but not here).
**Why:** Rule 10 — members may read only their own bookings; another member's booking id must return `404 BOOKING_NOT_FOUND`. Admins may read any in-org booking.
**Fix:**
```python
# After (added right after the None check)
if user.role != "admin" and booking.user_id != user.id:
    raise AppError(404, "BOOKING_NOT_FOUND", "Booking not found")
```
**Branch:** `fix/bug-15-booking-idor` (9863bb2)
**Test:** PASS — member A reads member B's booking → 404; owner → 200; admin → 200.

---

## FIX #16 — Cancel doesn't invalidate the availability cache
**File:** `app/routers/bookings.py` · **Function:** `cancel_booking` · **Line(s):** ~216–218
**Bug:** `cancel_booking` invalidated the usage-report cache but never the availability cache, so a cancelled booking kept showing as busy.
**Why:** Rule 13 — availability must reflect the current state immediately.
**Fix:**
```python
# After (added alongside invalidate_report)
cache.invalidate_availability(booking.room_id, booking.start_time.date().isoformat())
```
**Branch:** `fix/bug-16-cancel-avail-cache` (fe44797)
**Test:** PASS — book future date → availability shows busy → cancel → availability shows empty.

---

## FIX #17 — Stats race condition (concurrent create/cancel undercounts)
**File:** `app/services/stats.py` · **Function:** `record_create` + `record_cancel` · **Line(s):** ~14–30
**Bug:** Both functions do an unlocked read-modify-write of `_stats[room_id]` split by `_aggregate_pause()`. Concurrent updates for the same room read the same snapshot and clobber each other, losing count/revenue updates.
**Why:** Rule 14 — room stats must stay consistent with the bookings, including under bursts of concurrent activity.
**Fix:**
```python
# After (both functions wrapped in a module-level lock)
import threading
_stats_lock = threading.Lock()
def record_create(room_id, price_cents):
    with _stats_lock:
        current = _stats.get(room_id, {"count": 0, "revenue": 0})
        count, revenue = current["count"], current["revenue"]
        _aggregate_pause()
        _stats[room_id] = {"count": count + 1, "revenue": revenue + price_cents}
def record_cancel(room_id, price_cents):
    with _stats_lock:
        current = _stats.get(room_id, {"count": 0, "revenue": 0})
        count, revenue = current["count"], current["revenue"]
        _aggregate_pause()
        _stats[room_id] = {"count": max(0, count - 1), "revenue": revenue - price_cents}
```
Note: single global lock serializes all rooms (acceptable per challenge scope; per-room locking is an optional contention optimization only). The asymmetric revenue floor is addressed separately in #17b.
**Branch:** `fix/bug-17-stats-race` (95d8138)
**Test:** PASS — 10 concurrent creates one room: buggy main gave count=1/revenue=100; after fix count=10/revenue=1000. pytest smoke 1 passed.

---

## FIX #17b — Asymmetric floor: count clamped at 0, revenue not
**File:** `app/services/stats.py` · **Function:** `record_cancel` · **Line(s):** ~24–33
**Bug:** `record_cancel` clamps `count` at `max(0, count - 1)` but subtracts from `revenue` with no floor. When cancels outrun tracked creates for a room (e.g. empty `_stats` after a restart, or a cancel with no matching create in-process), `count` sticks at 0 while `revenue` goes negative. This is an arithmetic asymmetry, NOT a race, so #17's `_stats_lock` does not resolve it.
**Why:** Rule 14 — room stats must stay consistent with the bookings; an aggregate revenue should never be negative.
**Verification (reproduced on main which already has #17's lock):**
- [A] fresh room, 1× `record_cancel(1000)` → `{count: 0, revenue: -1000}` (negative)
- [B] create ×1 then cancel ×2 (500 each) → `{count: 0, revenue: -500}` (negative)
- [C] 10 concurrent creates one room (happy path) → `{count: 10, revenue: 7000}` (unaffected)
**Fix:**
```python
# Before
_stats[room_id] = {"count": max(0, count - 1), "revenue": revenue - price_cents}
# After  (floor revenue at 0 to match the count floor)
_stats[room_id] = {"count": max(0, count - 1), "revenue": max(0, revenue - price_cents)}
```
Note: symmetric one-line floor mirroring the existing count floor. No-op on the happy path (creates ≥ cancels), so the API contract is unchanged; it only clamps the underflow edge case. Genuinely reproducible AFTER #17's lock, so a dedicated branch is warranted (not "resolved-by-#17").
**Branch:** `fix/bug-17b-revenue-floor` (babbdc5)
**Test:** PASS — scenarios A/B showed revenue −1000/−500 on main (FAIL); after fix both floor to 0 and happy-path C stays count=10/revenue=7000. pytest smoke 1 passed.

---

## FIX #18 — Cross-org data leak via export include_all + room_id
**File:** `app/services/export.py` · **Function:** `generate_export` · **Line(s):** ~48–50
**Bug:** With `include_all=True` and a `room_id`, the code called `fetch_bookings_raw`, which filtered only by `room_id` with no org scoping.
**Why:** Rule 9 — a user may only act on data in their own org; cross-org resource ids must behave as non-existent.
**Fix:**
```python
# Before
if include_all:
    if room_id is not None:
        rows = fetch_bookings_raw(db, room_id)
    else:
        rows = _fetch_scoped(db, org_id, None, None)
# After
if include_all:
    rows = _fetch_scoped(db, org_id, None, room_id)
```
(`fetch_bookings_raw` left in place per the minimal-fix rule; it is simply no longer called.)
**Branch:** `fix/bug-18-export-org-scope` (caca958)
**Test:** PASS — Org B admin exports Org A's `room_id` with `include_all=true` → header-only CSV.

---

## FIX #19 — Rate limiter race condition bypasses the 20-req/60s limit
**File:** `app/services/ratelimit.py` · **Function:** `record_and_check` · **Line(s):** ~19–31
**Bug:** The read-trim-append-write of `_buckets[user_id]` (split by `_settle_pause()`) has no lock, so concurrent requests from one user read the same bucket snapshot, undercount, and slip past the 20-req/60s limit.
**Why:** Rule 5 — the rate limit must hold under concurrent requests.
**Fix:**
```python
# After (bucket read-trim-append-write wrapped in a module-level lock)
import threading
_buckets_lock = threading.Lock()
def record_and_check(user_id):
    now = time.time()
    with _buckets_lock:
        bucket = _buckets.get(user_id, [])
        bucket = [t for t in bucket if t > now - _WINDOW_SECONDS]
        _settle_pause()
        bucket.append(now)
        _buckets[user_id] = bucket
        if len(bucket) > _MAX_REQUESTS:
            raise AppError(429, "RATE_LIMITED", "Too many booking requests")
```
**Branch:** `fix/bug-19-ratelimit-race` (2026788)
**Test:** PASS — 25 concurrent requests one user: buggy main let all 25 through (0 limited); after fix exactly 20 succeed, 5 get 429. pytest smoke 1 passed.

---

## FIX #20 — Create doesn't invalidate the usage-report cache
**File:** `app/routers/bookings.py` · **Function:** `create_booking` · **Line(s):** ~120–122
**Bug:** `create_booking` invalidated the availability cache but never the usage-report cache (the mirror image of Bug 16), so a cached report kept stale counts after a new booking.
**Why:** Rule 12 — the usage report must reflect the current state immediately.
**Fix:**
```python
# After (added alongside invalidate_availability)
cache.invalidate_report(user.org_id)
```
**Branch:** `fix/bug-20-create-report-cache` (dc190b0)
**Test:** PASS — populate usage-report cache → create booking in range → report count reflects the new booking.

---

## FIX #21 — Concurrent duplicate registration crashes instead of returning 409
**File:** `app/routers/auth.py` · **Function:** `register` · **Line(s):** ~26–73
**Bug:** `register()` does check-then-insert for org-name and `(org_id, username)` uniqueness with no exception handling. Under concurrent duplicate registration the losing request's `db.commit()` raises `IntegrityError` (models.py enforces `Organization.name` unique and `UniqueConstraint(org_id, username)`). Unhandled, it surfaces as a raw 500 instead of the documented 409 USERNAME_TAKEN.
**Why:** Rule 15 — a duplicate username in an org must return 409 USERNAME_TAKEN; the API contract has no 500 for this input.
**Verification (reproduced on main):** deterministic username race (concurrent winner commits inside register's SELECT→commit window) → 500 Internal Server Error.
**Fix:**
```python
from sqlalchemy.exc import IntegrityError
# org insert — After
if org is None:
    org = Organization(name=payload.org_name)
    db.add(org)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        org = db.query(Organization).filter(Organization.name == payload.org_name).first()
        role = "member"
    else:
        db.refresh(org)
# user insert — After
db.add(user)
try:
    db.commit()
except IntegrityError:
    db.rollback()
    raise AppError(409, "USERNAME_TAKEN", "Username already taken in this organization")
db.refresh(user)
```
Note: guards BOTH inserts. Org-name race → rollback, adopt the now-existing org, demote role admin→member. Username race → rollback, 409 USERNAME_TAKEN. Happy path is byte-for-byte unchanged (the try/except only engages on an actual constraint violation). Preserves bug #4's sequential-duplicate 409.
**Branch:** `fix/bug-21-register-race` (f261fd8) — pushed, awaiting merge.
**Test:** PASS — deterministic race returned 500 on main; after fix returns 409. Realistic 8-thread barrier burst on the same brand-new (org, username) → exactly one 201, seven 409, ZERO 500, one org row, one user row. Happy paths (new org 201/admin, existing org 201/member, sequential dup 409) intact. pytest smoke 1 passed.

---

*End of consolidated fix-note compilation. All 22 fix sites (#1–#21 + #17b) covered.*
