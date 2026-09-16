#!/usr/bin/env bash
# Chạy TRÊN server, trong <repo>/deploy. Idempotent — chạy lại bao nhiêu lần cũng được.
#   ./deploy.sh              -> build image từ HEAD hiện tại của repo và (re)start
#   PULL=1 ./deploy.sh       -> git pull --ff-only trước rồi mới build
# Khi đã chuyển sang image chính thức (compose không còn khối build:), script tự pull image.
set -euo pipefail
cd "$(dirname "$0")"

[[ -f .env ]] || { echo "Thiếu deploy/.env — copy từ .env.example rồi điền giá trị"; exit 1; }
grep -qE '^MOCK_API_KEYS=.*sk_' .env || { echo "MOCK_API_KEYS trong .env phải có key bắt đầu bằng sk_"; exit 1; }
grep -qE 'CHANGE_ME' .env && { echo ".env vẫn còn giá trị CHANGE_ME"; exit 1; }

if [[ "${PULL:-0}" == "1" ]]; then
  git -C .. pull --ff-only
fi
echo "repo @ $(git -C .. rev-parse --short HEAD) — $(git -C .. log -1 --format=%s)"

if grep -qE '^\s+build:' docker-compose.yml; then
  docker compose build --pull
else
  docker compose pull
fi
docker compose up -d --remove-orphans

echo "Đợi clinic-mock healthy..."
for _ in $(seq 1 20); do
  st=$(docker inspect -f '{{.State.Health.Status}}' clinic-mock 2>/dev/null || true)
  [[ "$st" == "healthy" ]] && break
  sleep 3
done
docker compose ps
[[ "${st:-}" == "healthy" ]] || { echo "clinic-mock chưa healthy — xem: docker compose logs clinic-mock"; exit 1; }

echo "Image digest đang chạy:"
docker inspect -f '{{index .RepoDigests 0}} {{.Id}}' "$(docker compose images -q clinic-mock)" 2>/dev/null || true
docker image prune -f >/dev/null
