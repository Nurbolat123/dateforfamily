#!/bin/bash
# Резервная копия базы данных сервиса знакомств.
#
# Что делает: сохраняет базу в сжатый файл с датой в имени и удаляет
# копии старше RETENTION_DAYS дней. Рассчитан на ежедневный запуск через
# cron (см. DEPLOY.md, раздел "Резервные копии").
#
# Перед первым запуском:
# 1. Впишите ниже те же DB_NAME/DB_USER, что и в вашем .env (в DATABASE_URL).
# 2. Настройте файл ~/.pgpass, чтобы пароль не пришлось вводить вручную
#    (иначе автоматический запуск по расписанию не сработает) — см. DEPLOY.md.

set -euo pipefail

DB_NAME="dateforfamily"
DB_USER="dateforfamily"
DB_HOST="127.0.0.1"
BACKUP_DIR="/var/backups/dateforfamily"
RETENTION_DAYS=14

mkdir -p "$BACKUP_DIR"

timestamp=$(date +%Y-%m-%d_%H-%M-%S)
final_file="$BACKUP_DIR/dateforfamily_${timestamp}.sql.gz"
tmp_file="${final_file}.tmp"

# Пишем во временный файл и переименовываем только при успехе — если
# pg_dump оборвётся с ошибкой, недописанный файл не будет выглядеть как
# настоящая (но пустая) резервная копия.
cleanup() { rm -f "$tmp_file"; }
trap cleanup EXIT

pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" | gzip > "$tmp_file"
mv "$tmp_file" "$final_file"
trap - EXIT

echo "Резервная копия сохранена: $final_file"

find "$BACKUP_DIR" -name "dateforfamily_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
