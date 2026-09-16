#!/usr/bin/env bash
# Kiểm tra sau deploy và trước mỗi lần chấm điểm. Chạy từ máy bất kỳ.
#   ./smoke.sh https://clinic-mock.example.com sk_grading_xxx
set -euo pipefail
BASE="${1:?base url, vd https://clinic-mock.example.com}"
KEY="${2:?api key sk_...}"
pass() { echo "  OK    $1"; }
fail() { echo "  FAIL  $1"; exit 1; }

echo "1. /health"
[[ "$(curl -fsS "$BASE/health")" == '{"status":"ok"}' ]] && pass "health" || fail "health"

echo "2. Không key -> 401"
[[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/v1/patients?phone=0912345600")" == "401" ]] \
  && pass "401 khi thiếu key" || fail "auth không hoạt động"

echo "3. Có key -> tìm được pt_3391"
curl -fsS "$BASE/v1/patients?phone=0912345600" -H "Authorization: Bearer $KEY" | grep -q pt_3391 \
  && pass "GET /v1/patients" || fail "GET /v1/patients"

echo "4. apt_00417 đọc được"
curl -fsS "$BASE/v1/appointments/apt_00417" -H "Authorization: Bearer $KEY" | grep -q '"appointment_id"' \
  && pass "GET /v1/appointments/{id}" || fail "GET /v1/appointments/{id}"

echo "5. /_harness/state trả lời (chỉ harness gọi — bot KHÔNG gọi, §4.2.4)"
curl -fsS "$BASE/_harness/state" -H "Authorization: Bearer $KEY" >/dev/null \
  && pass "GET /_harness/state" || fail "GET /_harness/state"

echo "6. TLS / độ trễ"
curl -fsS -o /dev/null -w '  TLS verify=%{ssl_verify_result} http=%{http_version} total=%{time_total}s\n' "$BASE/health"

echo "7. /_harness/version (§4.2.1 — bản mentor hiện CHƯA có; bắt buộc khi dùng image chính thức)"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/_harness/version" -H "Authorization: Bearer $KEY")
if [[ "$code" == "200" ]]; then
  curl -s "$BASE/_harness/version" -H "Authorization: Bearer $KEY"; echo; pass "version"
else
  echo "  WARN  /_harness/version -> HTTP $code"
fi
