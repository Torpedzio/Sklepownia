#!/bin/bash
# Backups of shops in the restic repository, run by the platform's worker in a throwaway container
# (backend/shops/provisioning/container.py).
#
# The worker passes the repository (RESTIC_REPOSITORY, RESTIC_PASSWORD, RESTIC_CACHE_DIR) and, for one shop,
# SHOP (shop-<id>, the snapshots' host), SHOP_DB (its database at DB_HOST, root password in MYSQL_PWD)
# and the shop's volume at /shop/files.
#
#   shop-backup backup <tag> [path…]   copy the shop's files and database; paths in the volume to leave out
#                                      (caches); prints restic's summary as JSON
#   shop-backup restore <snapshot>     put the shop's database and files back as they were in the snapshot
#   shop-backup snapshots              every snapshot in the repository, as JSON
#   shop-backup forget <snapshot…>     remove snapshots; their data stays until prune
#   shop-backup prune                  free the space of removed snapshots
set -euo pipefail

FILES=/shop/files
DUMP=/shop/database.sql

# Waits for another restic process instead of failing, e.g. a backup the owner asked for during the nightly prune.
LOCK=(--retry-lock 30m)

ensure_repository() {
  if ! restic cat config >/dev/null 2>&1; then
    # Another backup may create it at the same moment; then it is there all the same.
    restic init >/dev/null 2>&1 || restic cat config >/dev/null
  fi
}

check_files() {
  # The worker mounts the shop's volume here; without it there would be nothing to copy or restore into.
  if ! mountpoint -q "$FILES"; then
    echo "The shop's files are not mounted at $FILES" >&2
    exit 2
  fi
}

database() {
  mariadb --host="$DB_HOST" --user=root "$@"
}

backup() {
  local tag=$1
  shift
  check_files
  ensure_repository
  # A consistent copy without locking the shop: every table is InnoDB.
  mariadb-dump --host="$DB_HOST" --user=root --single-transaction --quick --routines --triggers --events \
    --hex-blob "$SHOP_DB" > "$DUMP"
  local excludes=()
  for path in "$@"; do
    excludes+=(--exclude "$FILES/$path")
  done
  restic backup "${LOCK[@]}" --host "$SHOP" --tag "$tag" --json --quiet "${excludes[@]}" /shop
}

restore() {
  local snapshot=$1
  check_files
  # The database comes out of the repository first, so a missing or damaged snapshot leaves the shop untouched.
  restic dump "${LOCK[@]}" "$snapshot" "$DUMP" > /tmp/database.sql
  # Privileges on the database outlive it, so the shop's user can use the new one at once.
  database -e "DROP DATABASE IF EXISTS \`$SHOP_DB\`;
    CREATE DATABASE \`$SHOP_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
  database "$SHOP_DB" < /tmp/database.sql
  # Files that came after the snapshot go, caches left out of it too.
  restic restore "${LOCK[@]}" "$snapshot:$FILES" --target "$FILES" --delete --quiet
}

case "${1:-}" in
  backup) shift; backup "$@" ;;
  restore) restore "$2" ;;
  # A wrong password fails here rather than listing nothing.
  snapshots) ensure_repository; restic snapshots --no-lock --json ;;
  forget) shift; restic forget "${LOCK[@]}" "$@" ;;
  prune) restic prune "${LOCK[@]}" --quiet ;;
  *)
    echo "usage: shop-backup backup <tag> [path…] | restore <snapshot> | snapshots | forget <snapshot…> | prune" >&2
    exit 64
    ;;
esac
