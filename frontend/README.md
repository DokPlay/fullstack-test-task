# Frontend

Next.js-приложение для панели мониторинга файлового обменника.

## Что внутри

- layered-структура `shared -> entities -> features -> widgets`;
- отдельный API-клиент и конфиг `NEXT_PUBLIC_API_URL`;
- realtime-обновления через SSE snapshot/patch с polling fallback;
- upload применяет returned file локально и не делает лишний refetch при активном SSE;
- типизированный UI с `typecheck`, `lint` и production build;
- standalone-сборка для Docker.

## Команды

```bash
npm install
npm run typecheck
npm run lint
npm run build
npm run dev
```

По умолчанию frontend ожидает backend на `http://localhost:8000`.

Если нужен другой адрес:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Полное описание проекта и Docker-инструкции находятся в корневом [README](../README.md).
