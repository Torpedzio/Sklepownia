# Backups of the shops: restic keeps deduplicated, encrypted snapshots of each shop's files and database dump.
# The MariaDB image brings the client (mariadb-dump) of the same version as the shops' database.
# The platform's worker runs it for one task at a time and removes the container afterwards (see shop-backup.sh).
FROM restic/restic:0.19.1 AS restic

FROM mariadb:11.8
COPY --from=restic /usr/bin/restic /usr/local/bin/restic
COPY shop-backup.sh /usr/local/bin/shop-backup
RUN chmod +x /usr/local/bin/shop-backup
ENTRYPOINT ["shop-backup"]
