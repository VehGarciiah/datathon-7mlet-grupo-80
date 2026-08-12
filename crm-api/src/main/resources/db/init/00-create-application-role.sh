#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set=crm_app_password="$CRM_APP_PASSWORD" <<-'EOSQL'
SELECT format(
    'CREATE ROLE crm_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
    :'crm_app_password'
) \gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO crm_app', current_database()) \gexec
EOSQL
