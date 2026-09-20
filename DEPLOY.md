# Как запустить сервис на сервере

Инструкция рассчитана на то, что вы делаете это первый раз. Все команды
нужно вводить в терминал сервера (подключение по SSH), по одной,
дожидаясь, пока предыдущая закончится.

## 1. Выбор сервера

По закону Казахстана о персональных данных, сервер и база данных должны
физически находиться в Казахстане. При выборе VPS (виртуального сервера)
ищите хостинг с датацентром в Казахстане (обычно указано на сайте
хостинга: "Алматы" или "Астана"). Минимальные требования для этого
проекта:

- Ubuntu 22.04 или 24.04 (Linux)
- 1–2 ГБ оперативной памяти достаточно для старта
- Доступ по SSH (это даст сам хостинг после оплаты — обычно приходит
  письмо с IP-адресом, логином и паролем или файлом-ключом)

## 2. Первый вход и базовая настройка

Подключитесь к серверу (замените `ВАШ_IP` на адрес, который дал хостинг):

```
ssh root@ВАШ_IP
```

Обновите систему и создайте отдельного пользователя для сервиса (работать
от имени `root` постоянно небезопасно):

```
apt update && apt upgrade -y
adduser dateforfamily
usermod -aG sudo dateforfamily
su - dateforfamily
```

Дальше все команды выполняются уже от имени `dateforfamily`.

## 3. Установка Python, PostgreSQL и git

```
sudo apt install -y python3.12 python3.12-venv postgresql git
```

Проверьте, что всё установилось:

```
python3.12 --version
psql --version
git --version
```

## 4. База данных

Создайте пользователя и базу данных PostgreSQL (замените
`ПРИДУМАЙТЕ_ПАРОЛЬ` на свой надёжный пароль — он же пойдёт в `.env`):

```
sudo -u postgres psql -c "CREATE USER dateforfamily WITH PASSWORD 'ПРИДУМАЙТЕ_ПАРОЛЬ';"
sudo -u postgres psql -c "CREATE DATABASE dateforfamily OWNER dateforfamily;"
```

## 5. Код проекта

```
cd ~
git clone https://github.com/Nurbolat123/dateforfamily.git
cd dateforfamily
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

## 6. Настройка `.env`

```
cp .env.example .env
nano .env
```

Впишите реальные значения:

- `BOT_TOKEN` — токен вашего бота от @BotFather в Telegram
- `DATABASE_URL` — `postgresql+asyncpg://dateforfamily:ПРИДУМАЙТЕ_ПАРОЛЬ@localhost:5432/dateforfamily`
  (тот же пароль, что задали в шаге 4)
- `ADMIN_USERNAME` и `ADMIN_PASSWORD` — логин и пароль для входа в
  админку. **Пароль обязателен** — без него админка откажется
  запускаться (это сделано специально, см. шаг 8 в CLAUDE.md)

Сохраните файл: `Ctrl+O`, `Enter`, затем `Ctrl+X` для выхода.

## 7. Применение миграций (создание таблиц в базе)

```
.venv/bin/alembic upgrade head
```

Если команда прошла без ошибок — таблицы созданы.

## 8. Автозапуск бота и админки (systemd)

Скопируйте готовые файлы служб (они уже лежат в репозитории, в папке
`deploy/`) в системную папку и включите автозапуск:

```
sudo cp deploy/dateforfamily-bot.service /etc/systemd/system/
sudo cp deploy/dateforfamily-admin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dateforfamily-bot
sudo systemctl enable --now dateforfamily-admin
```

Проверьте, что обе службы запустились:

```
sudo systemctl status dateforfamily-bot
sudo systemctl status dateforfamily-admin
```

Должно быть написано зелёным `active (running)`. Если что-то не так,
подробности покажет:

```
journalctl -u dateforfamily-bot -n 50
journalctl -u dateforfamily-admin -n 50
```

Благодаря `Restart=always` в файлах служб, если бот или админка упадут
из-за ошибки, они сами перезапустятся через несколько секунд. Если
перезагрузится весь сервер — они тоже запустятся автоматически, без
вашего участия.

## 9. Доступ к админке

Админка специально запущена только для самого сервера (`127.0.0.1`) —
она не видна напрямую из интернета. Это осознанное решение: без своего
домена нет смысла настраивать https, а без https нельзя честно защитить
пароль администратора, идущий по сети. Чтобы открыть админку у себя в
браузере, используйте SSH-туннель — команда на **своём компьютере** (не
на сервере):

```
ssh -L 8000:localhost:8000 dateforfamily@ВАШ_IP
```

Оставьте это окно терминала открытым и откройте в браузере:
`http://127.0.0.1:8000/users` — попросит логин и пароль из `.env`.

Если в будущем понадобится открыть админку для кого-то ещё без доступа
по SSH — понадобится свой домен и настройка https через nginx; тогда
стоит вернуться к этому вопросу отдельным шагом.

## 10. Резервные копии базы данных

Скопируйте скрипт резервного копирования и сделайте его исполняемым:

```
sudo mkdir -p /var/backups/dateforfamily
sudo chown dateforfamily:dateforfamily /var/backups/dateforfamily
cp deploy/backup-db.sh ~/backup-db.sh
chmod +x ~/backup-db.sh
```

Откройте `~/backup-db.sh` и проверьте, что `DB_NAME` и `DB_USER`
совпадают с тем, что вы указали в `.env` (по умолчанию оба — `dateforfamily`).

Чтобы резервное копирование работало по расписанию без ввода пароля
вручную, создайте файл `~/.pgpass`:

```
echo "127.0.0.1:5432:dateforfamily:dateforfamily:ПРИДУМАЙТЕ_ПАРОЛЬ" > ~/.pgpass
chmod 600 ~/.pgpass
```

(вместо `ПРИДУМАЙТЕ_ПАРОЛЬ` — тот же пароль базы данных, что в `.env`).

Проверьте, что скрипт работает:

```
~/backup-db.sh
ls -la /var/backups/dateforfamily
```

Должен появиться файл вида `dateforfamily_2026-01-15_03-00-00.sql.gz`.

Настройте автоматический запуск каждую ночь через `cron`:

```
crontab -e
```

Добавьте в конец файла строку (запуск каждый день в 3 часа ночи):

```
0 3 * * * /home/dateforfamily/backup-db.sh >> /home/dateforfamily/backup.log 2>&1
```

Сохраните и закройте редактор. Резервные копии старше 14 дней скрипт
удаляет автоматически — сколько хранить, можно поменять внутри самого
скрипта (переменная `RETENTION_DAYS`).

**Важно:** резервные копии сейчас хранятся на том же сервере. Это
защищает от ошибок в самой программе или случайного удаления данных, но
не от поломки самого сервера. Когда сервис начнёт работать с реальными
людьми, стоит дополнительно скачивать копии на другой сервер или в
облачное хранилище — это можно сделать отдельным шагом позже.

## 11. Как обновить код в будущем

Когда в проект добавляются новые шаги (например, шаг 10 и далее) или
исправления, обновление на сервере делается так:

```
cd ~/dateforfamily
git pull
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
sudo systemctl restart dateforfamily-bot
sudo systemctl restart dateforfamily-admin
```

## 12. Проверка, что всё работает

- Напишите вашему боту в Telegram `/start` — должен ответить.
- Откройте админку через SSH-туннель (шаг 9) — должна открыться страница
  со списком анкет.
- Проверьте автозапуск: `sudo reboot`, подождите минуту, подключитесь
  заново и проверьте `sudo systemctl status dateforfamily-bot` — должно
  быть `active (running)` без вашего вмешательства.
