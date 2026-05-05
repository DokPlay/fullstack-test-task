# Secure File Exchange Dashboard

[English version](./README.md)

Secure File Exchange Dashboard - это fullstack MVP файлообменника. Он позволяет загружать документы, хранит метаданные файлов в PostgreSQL, обрабатывает файлы асинхронно через Celery, выявляет подозрительные признаки, создает алерты и обновляет дашборд в реальном времени через Server-Sent Events.

Проект включает FastAPI backend, Next.js frontend, PostgreSQL, Redis, Celery worker и Celery Beat watchdog. Все сервисы запускаются через Docker Compose для удобной локальной проверки.

## Возможности

- Загрузка файлов через веб-интерфейс и REST API.
- Потоковая запись файлов через `aiofiles`, без полного чтения файла в память.
- Настраиваемый жесткий лимит загрузки: слишком большой upload получает `413` до заполнения локального хранилища.
- Хранение метаданных, статусов обработки, результатов проверки и алертов в PostgreSQL.
- Фоновая обработка через Celery с Redis broker/result backend.
- Атомарный claim файла перед обработкой, чтобы повторная доставка Celery не обрабатывала один файл дважды.
- Watchdog для восстановления stale `processing` и stale `uploaded` файлов.
- Выявление подозрительных расширений, слишком больших файлов и MIME-конфликта у PDF.
- Извлечение метаданных для текстовых файлов и PDF через чанковое чтение.
- Realtime-дашборд через SSE с initial snapshot и patch-событиями.
- Polling оставлен только как fallback, если realtime недоступен.
- Каскадное удаление алертов при удалении файла.
- Слоистая backend-архитектура и feature-sliced структура frontend.

## Технологии

Backend:

- Python 3.14
- FastAPI
- SQLAlchemy async ORM
- Alembic
- PostgreSQL
- Redis
- Celery и Celery Beat
- aiofiles

Frontend:

- Next.js 16
- React 18
- TypeScript
- React-Bootstrap
- Bootstrap 5

Инфраструктура:

- Docker Compose
- PostgreSQL 16
- Redis 7

## Архитектура

### Backend

Backend разделен на явные слои:

- `backend/src/api` - FastAPI routes и dependency providers.
- `backend/src/core` - settings, database factory, DI container и файловое хранилище.
- `backend/src/repositories` - доступ к данным.
- `backend/src/services` - бизнес-логика, обработка файлов, события и queue abstraction.
- `backend/src/tasks.py` - Celery worker entrypoint.

Ключевые решения:

- `ApplicationContainer` является composition root для settings, storage, repositories, services, event bus и lifecycle базы данных.
- FastAPI зависимости получают сервисы из контейнера, а не создают их внутри route handlers.
- Web app использует queue adapter и не импортирует Celery worker entrypoint напрямую.
- Redis publisher и SQLAlchemy engine закрываются через FastAPI lifespan.
- Обработка начинается через conditional database update, что делает duplicate worker delivery идемпотентным.
- Celery Beat периодически возвращает stale файлы в очередь или помечает их как `failed` после лимита попыток.
- Celery worker и beat в Docker сбрасывают root-права через `--uid nobody --gid nogroup`.

### Frontend

Frontend организован по feature-sliced слоям:

- `frontend/src/app` - entrypoints Next.js.
- `frontend/src/widgets` - крупные блоки дашборда.
- `frontend/src/features` - загрузка файлов и мониторинг дашборда.
- `frontend/src/entities` - доменные типы, helpers статусов и entity UI.
- `frontend/src/shared` - переиспользуемые API, форматтеры и UI-утилиты.

Дашборд открывает SSE-соединение к `/events`, применяет initial snapshot, затем применяет patch-события без полного refetch после каждого realtime-события. Full refresh остается как ручной и fallback-сценарий.

## Запуск

Требования:

- Docker Desktop с поддержкой Compose.

Используйте стандартный Docker-запуск проекта.

Запустить стек:

```bash
docker compose -f docker-compose.dev.yml up
```

После запуска backend-контейнера применить миграции во втором терминале:

```bash
docker exec -it backend alembic upgrade head
```

Открыть фронт: [http://localhost:3000/test](http://localhost:3000/test)

Открыть бэк: [http://localhost:8000/docs](http://localhost:8000/docs)

Команда `docker compose ... up` работает в foreground и показывает логи, поэтому этот терминал нужно оставить открытым на время работы приложения.

## Дополнительные опции

Backend health check:

- Liveness: [http://localhost:8000/health/live](http://localhost:8000/health/live)
- Readiness: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)
- Legacy alias: [http://localhost:8000/health](http://localhost:8000/health)
- Prometheus: [http://localhost:8000/metrics](http://localhost:8000/metrics)

Стек мониторинга с Prometheus и Grafana:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.monitoring.yml --profile monitoring up -d
docker exec -it backend alembic upgrade head
```

URL мониторинга:

- Prometheus: [http://localhost:9090](http://localhost:9090)
- Grafana: [http://localhost:3001](http://localhost:3001)
- Логин Grafana: `admin`
- Пароль Grafana: `admin`
- Backend metrics: [http://localhost:8000/metrics](http://localhost:8000/metrics)
- Worker metrics: [http://localhost:9101/metrics](http://localhost:9101/metrics)
- Beat metrics: [http://localhost:9102/metrics](http://localhost:9102/metrics)

Grafana автоматически получает Prometheus datasource через provisioning. После входа можно открыть Explore и выполнить запросы `up`, `http_requests_total`, `file_upload_total`, `file_scan_total` или `celery_worker_tasks_completed_total`.

Запуск в detached mode:

```bash
docker compose -f docker-compose.dev.yml up -d
docker exec -it backend alembic upgrade head
```

Если терминал или CI-среда не поддерживает interactive TTY, миграции можно выполнить без `-it`:

```bash
docker exec backend alembic upgrade head
```

Принудительно пересобрать образы после изменений кода или зависимостей:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Остановить стек:

```bash
docker compose -f docker-compose.dev.yml down
```

Остановить стек и удалить PostgreSQL volume:

```bash
docker compose -f docker-compose.dev.yml down -v
```

## Управление миграциями

Для обычного свежего локального запуска нужна только эта команда миграций:

```bash
docker exec -it backend alembic upgrade head
```

Rollback-команды нужны для обслуживания, ошибочного релиза или контролируемого production rollback. Они не являются частью стандартного локального запуска.

Проверить текущую ревизию базы:

```bash
docker exec -it backend alembic current
```

Показать историю миграций:

```bash
docker exec -it backend alembic history --verbose
```

Откатить одну миграцию:

```bash
docker exec -it backend alembic downgrade -1
```

Откатиться к конкретной ревизии:

```bash
docker exec -it backend alembic downgrade <revision_id>
```

Вернуться на последнюю схему:

```bash
docker exec -it backend alembic upgrade head
```

Если терминал или CI-среда не поддерживает interactive TTY, выполняйте те же команды без `-it`. Перед любым downgrade сделайте backup PostgreSQL database или volume и `backend/storage/files`: откат схемы может удалить columns или constraints и не обязан восстановить данные, которые уже были преобразованы или удалены.

## Подключение к сайту или хостингу

Здесь указано, куда именно вставлять свой домен, IP сервера и настройки хостинга/proxy.

Пример значений ниже:

```text
IP сервера:         203.0.113.10
Основной сайт:      https://my-site.com
Файловый менеджер:  https://files.my-site.com/test
Backend API:        https://files.my-site.com/api
```

Это только пример. Замените `my-site.com`, `files.my-site.com` и `203.0.113.10` на свои реальные значения.

### 1. DNS домена

Это меняется не в файлах репозитория.

Откройте DNS-панель своего домена и создайте запись:

```text
Type: A
Name: files
Value: 203.0.113.10
```

После этого `files.my-site.com` будет указывать на сервер, где запущен этот Docker-проект.

### 2. Backend URL для готового frontend

Создайте новый локальный файл в корне проекта:

```text
.env
```

Вставьте в `.env` строку:

```env
NEXT_PUBLIC_API_URL=https://files.my-site.com/api
```

Если меняете backend `MAX_UPLOAD_SIZE_BYTES` в `.env.dev`, добавьте такое же значение в байтах в `.env`, чтобы UI проверял тот же лимит:

```env
NEXT_PUBLIC_MAX_UPLOAD_SIZE_BYTES=52428800
```

Почему это отдельный файл: Docker Compose автоматически читает `.env` для подстановки `${NEXT_PUBLIC_API_URL}` в `docker-compose.dev.yml`. Это значение используется при сборке Next.js frontend. Не коммитьте `.env`, если там production-значения.

### 3. Домены, которым backend разрешает запросы

Откройте существующий файл:

```text
.env.dev
```

Найдите или добавьте строку:

```env
ALLOWED_ORIGINS=https://files.my-site.com
```

Такое значение подходит, если пользователи открывают готовую страницу файлового менеджера на `https://files.my-site.com/test`.

Если основной сайт `https://my-site.com` сам вызывает backend API через свой интерфейс, укажите:

```env
ALLOWED_ORIGINS=https://my-site.com
```

Если нужно разрешить несколько сайтов, пишите через запятую:

```env
ALLOWED_ORIGINS=https://files.my-site.com,https://my-site.com
```

### 4. Reverse proxy или маршруты хостинга

Nginx не входит в этот репозиторий. Он настраивается на сервере или в панели хостинга.

Если Nginx установлен на Linux-сервере, создайте файл вне проекта, например:

```text
/etc/nginx/sites-available/file-manager.conf
```

Вставьте туда конфиг и замените `files.my-site.com` на свой домен файлового менеджера:

```nginx
server {
    listen 80;
    server_name files.my-site.com;

    location /api/events {
        proxy_pass http://127.0.0.1:8000/events;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 1h;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
    }
}
```

Если используется Caddy, Traefik, Cloudflare или панель хостинга вместо Nginx, создайте там такие же маршруты:

```text
https://files.my-site.com/      -> http://127.0.0.1:3000
https://files.my-site.com/api/  -> http://127.0.0.1:8000/
```

После этого backend API будет доступен так:

```text
https://files.my-site.com/api/files
https://files.my-site.com/api/alerts
https://files.my-site.com/api/events
```

### 5. Публичные порты

Обычно порты в `docker-compose.dev.yml` менять не нужно.

Текущие публичные порты:

```yaml
frontend: 3000
backend: 8000
database for local access: 5433
```

Меняйте `docker-compose.dev.yml` только если эти порты уже заняты на сервере. Меняется только левая часть:

```yaml
ports:
  - "8080:3000"
```

Тогда frontend будет доступен на host-порту `8080`, а внутри контейнера всё равно останется порт `3000`.

### 6. Запуск после изменения значений

После изменения `NEXT_PUBLIC_API_URL` пересоберите frontend, потому что это значение встраивается в browser bundle:

```bash
docker compose -f docker-compose.dev.yml up --build
docker exec -it backend alembic upgrade head
```

Откройте:

```text
https://files.my-site.com/test
```

### 7. Подключение с существующего сайта

Если нужен готовый UI, добавьте на существующий сайт ссылку или кнопку:

```text
https://files.my-site.com/test
```

Если у существующего сайта свой интерфейс, вызывайте backend API напрямую:

```text
POST https://files.my-site.com/api/files
GET  https://files.my-site.com/api/files
GET  https://files.my-site.com/api/events
```

В этом случае не забудьте разрешить домен основного сайта в `.env.dev`:

```env
ALLOWED_ORIGINS=https://my-site.com
```

### 8. Если используется только IP без домена

Для быстрой проверки без DNS и без reverse proxy:

Корневой `.env`:

```env
NEXT_PUBLIC_API_URL=http://203.0.113.10:8000
```

Существующий `.env.dev`:

```env
ALLOWED_ORIGINS=http://203.0.113.10:3000
```

Открыть:

```text
http://203.0.113.10:3000/test
```

Для production лучше использовать домен, HTTPS и reverse proxy.

## Конфигурация

Docker Compose читает backend-переменные из `.env.dev`.

Файл `.env.dev` намеренно оставлен в репозитории с demo/test credentials, чтобы проект запускался сразу после clone. Если вы замените эти demo-значения реальными серверными credentials, перед любым push добавьте `.env.dev` в `.gitignore`. Относитесь к реальным env-значениям как к ключам доступа к вашей программе и инфраструктуре: их нельзя случайно публиковать в GitHub или похожие облачные репозитории.

Основные backend-переменные:

| Переменная | Описание |
| --- | --- |
| `POSTGRES_HOST` | Хост PostgreSQL для backend, worker и beat. |
| `POSTGRES_PORT` | Порт PostgreSQL внутри Docker-сети. |
| `POSTGRES_DB` | Имя базы данных PostgreSQL. |
| `POSTGRES_USER` | Пользователь PostgreSQL. |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL. |
| `PGSSLMODE` | Режим SSL для PostgreSQL. Для локальной Docker-сети используется `disable`. |
| `DATABASE_POOL_SIZE` | Базовый размер пула SQLAlchemy-соединений на каждый backend-процесс. По умолчанию `10`. |
| `DATABASE_POOL_MAX_OVERFLOW` | Дополнительные временные SQLAlchemy-соединения сверх базового размера пула. По умолчанию `10`. |
| `DATABASE_POOL_RECYCLE_SECONDS` | Время жизни SQLAlchemy-соединения перед пересозданием. Значение `1800` помогает долгоживущим web/worker-процессам не держать stale PostgreSQL-соединения. |
| `REDIS_URL` | Redis URL для Celery и SSE pub/sub. |
| `ALLOWED_ORIGINS` | Список frontend origins, которым backend разрешает CORS-запросы. Значения разделяются запятыми. |
| `MAX_FILE_SIZE_BYTES` | Бизнес-порог проверки: принятые файлы выше этого размера помечаются как suspicious. |
| `MAX_UPLOAD_SIZE_BYTES` | Жесткий лимит приема upload. Держите его больше или равным `MAX_FILE_SIZE_BYTES`; более крупные файлы получают `413`. |
| `PROCESSING_TIMEOUT_SECONDS` | Возраст, после которого файл в обработке считается stale. |
| `PROCESSING_RECOVERY_INTERVAL_SECONDS` | Интервал watchdog-задачи Celery Beat. |
| `MAX_PROCESSING_ATTEMPTS` | Лимит попыток перед переводом файла в `failed`. |
| `DASHBOARD_EVENTS_CHANNEL` | Redis pub/sub канал для событий дашборда. |
| `DASHBOARD_EVENTS_HEARTBEAT_SECONDS` | Интервал SSE keepalive. |
| `DASHBOARD_EVENTS_RETRY_TIMEOUT_MS` | Подсказка браузеру для SSE reconnect. |
| `WORKER_METRICS_ENABLED` | Включает `/metrics` в worker/beat (`true`/`false`). |
| `WORKER_METRICS_PORT` | Порт для метрик worker/beat (например, `9101` и `9102`). |

Frontend-конфигурация:

| Переменная | Описание |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | Публичный URL backend для браузера. Docker Compose задает `http://localhost:8000`. |
| `NEXT_PUBLIC_MAX_UPLOAD_SIZE_BYTES` | Публичный лимит проверки файла в UI. Держите его синхронным с backend `MAX_UPLOAD_SIZE_BYTES`. |

## Локальная разработка

Backend:

```bash
cd backend
uv run --group dev pytest
uv run --group dev uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
uv run --group dev celery -A src.tasks.celery_app worker -l info
```

Frontend:

```bash
cd frontend
npm install
npm run typecheck
npm run lint
npm run build
npm run dev
```

## Проверка

Рекомендуемые проверки перед сдачей:

```bash
cd backend
uv run --group dev pytest
uv run python -m compileall src tests
```

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

Docker smoke checklist:

- Запустить стек: `docker compose -f docker-compose.dev.yml up`.
- Во втором терминале применить миграции: `docker exec -it backend alembic upgrade head`.
- Проверить `/health/live`, `/health/ready`, `/health`, `/docs`, `/metrics`, `/files`, `/alerts` и `/events`.
- Загрузить чистый текстовый файл и убедиться, что он становится `processed` и `clean`.
- Загрузить подозрительное расширение, например `.sh`, и убедиться, что файл становится `processed` и `suspicious`.
- Проверить скачивание файла, изменение title, удаление файла, ответы `404` и каскадное удаление алертов.
- Если включён мониторинг:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.monitoring.yml --profile monitoring up -d
```

- Проверить метрики:

  - Prometheus: [http://localhost:9090](http://localhost:9090)
  - Grafana: [http://localhost:3001](http://localhost:3001), логин `admin`, пароль `admin`
  - Backend metrics: [http://localhost:8000/metrics](http://localhost:8000/metrics)
  - Worker metrics: [http://localhost:9101/metrics](http://localhost:9101/metrics)
  - Beat metrics: [http://localhost:9102/metrics](http://localhost:9102/metrics)

Dev Celery worker использует `solo` pool, чтобы встроенный Prometheus endpoint показывал task counters из того же процесса, который выполняет задачи. Для production worker с высокой нагрузкой и `prefork` лучше использовать Prometheus multiprocess mode или отдельный Celery exporter.

## API endpoints

| Method | Path | Описание |
| --- | --- | --- |
| `GET` | `/health/live` | Проверка жизнеспособности процесса. |
| `GET` | `/health/ready` | Проверка готовности зависимостей (PostgreSQL + Redis). |
| `GET` | `/health` | Обратная совместимость: alias для `/health/ready`. |
| `GET` | `/metrics` | Prometheus-метрики (`requests`, системные и бизнес-метрики). |
| `GET` | `/files` | Список загруженных файлов. |
| `POST` | `/files` | Загрузка файла. |
| `GET` | `/files/{file_id}` | Получение одного файла. |
| `PATCH` | `/files/{file_id}` | Обновление title файла. |
| `DELETE` | `/files/{file_id}` | Удаление файла и связанных алертов. |
| `GET` | `/files/{file_id}/download` | Скачивание сохраненного файла. |
| `GET` | `/alerts` | Список алертов обработки. |
| `GET` | `/events` | SSE stream со snapshot и patch-событиями дашборда. |

Подозрительные файлы намеренно остаются доступными для скачивания. Флаг `requires_attention` и связанные алерты являются информационным слоем проверки: они предупреждают операторов о риске, но не помещают файл в карантин и не блокируют скачивание сохраненного файла.

## Production deployment guide

Стандартные Docker-команды выше предназначены для локальной проверки и разработки. Для production сохраняйте ту же архитектуру приложения, но переносите runtime-настройки и инфраструктуру в целевую среду.

Перед публикацией приложения на реальном домене:

- Направьте DNS на сервер и поставьте frontend/backend за HTTPS через reverse proxy или маршрутизатор хостинга.
- Храните реальные secrets вне Git. Оставляйте `.env.dev` demo-значения только для локального clone-and-run запуска, а production credentials держите в server environment, secret manager или приватном env-файле, который игнорируется Git.
- Укажите frontend `NEXT_PUBLIC_API_URL` на публичный backend URL, а backend `ALLOWED_ORIGINS` - на точный frontend domain или список domains.
- Используйте persistent storage для PostgreSQL data и uploaded files. Делайте backup базы и file storage вместе, потому что metadata и binaries относятся к одним и тем же file records.
- Для production лучше иметь отдельный Dockerfile или Compose profile: убрать `--reload`, запускать FastAPI от non-root пользователя, подключать writable volumes с корректным ownership и оставлять Celery worker/beat включенными.
- Выполняйте `alembic upgrade head` как контролируемый release step перед обслуживанием новой backend version.
- После deployment проверьте `/health`, `/docs`, `/files`, `/alerts` и `/events`.

Не публикуйте приложение в открытый интернет без авторизации. Используйте production auth guidance ниже до того, как реальные пользователи или внешний traffic получат доступ к сервису.

## Production handoff notes

Репозиторий готов для технического review и локальной проверки через Docker. Для реального production deployment нужно заменить dev-настройки на настройки целевой среды:

- Использовать надежные credentials и secrets вне репозитория.
- Оставить backend command в review/dev Compose без hot reload. Если нужен отдельный hot-reload profile для локальной разработки, не используйте его в production.
- Хранить PostgreSQL data и file storage в persistent volumes целевой инфраструктуры.
- Выполнять миграции как контролируемый release step: `alembic upgrade head`.
- Указать `NEXT_PUBLIC_API_URL` на публичный backend URL.
- Поставить frontend и backend за HTTPS/reverse proxy.
- Оставить Celery worker и beat под non-root пользователями, как уже настроено в Docker Compose.

### Docker users и права на файлы

Dev-контейнер backend намеренно оставлен с дефолтным пользователем контейнера. В `docker-compose.dev.yml` сервис backend монтирует `./backend:/backend`; приложение также создает загруженные файлы в `backend/storage/files`. Если поставить `USER nobody` на этот dev FastAPI контейнер, на Windows/Linux host mounts можно получить ошибки записи в storage, bytecode/cache директории или tooling миграций.

Compose backend command запускает Uvicorn без `--reload`, чтобы стандартный Docker-запуск был стабильным для долгоживущих SSE-соединений. Если нужен hot reload во время разработки, добавьте его только в локальный override/profile. Celery worker и beat уже сбрасывают права через `--uid nobody --gid nogroup`. Для production лучше сделать отдельный production Dockerfile/Compose profile: запускать FastAPI от non-root пользователя, подключать writable volumes с корректными ownership/permissions и хранить runtime storage вне source bind mount.

### Авторизация обязательна в production

Перед публикацией приложения на своем сервере, домене или в публичной сети обязательно закройте frontend и backend авторизацией. Если оставить приложение доступным без auth-boundary, посторонний пользователь сможет обращаться к `/files`, `/alerts`, `/events` и `/files/{file_id}/download`. SSE stream `/events` передает realtime snapshot и patch-события с метаданными файлов и деталями алертов, поэтому публичный доступ может раскрыть рабочую информацию и данные документов.

Перед production traffic используйте один из корректных вариантов:

- Для single-admin или closed-team deployment закройте весь домен на уровне reverse proxy или хостинга: Nginx Basic Auth, Cloudflare Access, access control панели хостинга или private network access.
- Для multi-user access внедрите application auth: login/password, надежное хеширование паролей, session cookie или JWT, роли пользователей и owner/team access checks для `/files`, `/alerts`, `/events` и downloads.
- Не считайте секретный token, встроенный во frontend code, полноценной защитой. Все, что отправлено в браузер, пользователь может посмотреть.

Стандартные локальные Docker-команды выше остаются без изменений. Это требование авторизации относится к публикации приложения на реальном сервере, домене или в публичной сети.

## Текущий статус проверки

Проект проверен backend-тестами, frontend typecheck/lint/build, Docker startup, миграциями, Celery worker processing, SSE events, upload/download/update/delete flows, validation errors и alert cleanup.
