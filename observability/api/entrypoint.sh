#!/bin/sh
set -eu

# Os diretórios são exclusivos do runtime; o processo da aplicação continua sem root.
chown -R datathon:datathon /app/artifacts/serving /var/log/datathon 2>/dev/null || true

exec gosu datathon "$@"
