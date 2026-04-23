# Network King

Network King is a mobile-first FastAPI web app for running a QR-driven networking game. Public visitors can follow event progress, networkers can scan characters and save notes to unlock the next level, and admins can manage events, accounts, characters, CSV transfers, images, and printable badge downloads.

## Stack

- FastAPI + Jinja templates
- SQLAlchemy
- Signed cookie sessions
- PostgreSQL-ready configuration
- Local filesystem storage for development, with a Google Cloud Storage adapter for production

## Local Setup

1. Create a Python 3.12+ virtual environment.
2. Install dependencies:

```bash
pip install -e ".[test]"
```

3. Copy the example environment and adjust values as needed:

```bash
cp .env.example .env
```

4. Run the app:

```bash
uvicorn app.main:app --reload
```

5. Seed the first admin account by setting `SEED_ADMIN_LOGIN` and `SEED_ADMIN_PASSWORD`, then either start the app or run:

```bash
python -m app.seed_admin
```

## Docker

Build the image:

```bash
docker build -t network-king .
```

Run it locally on port `8080`:

```bash
docker run \
  -p 8080:8080 \
  -e SECRET_KEY=change-me \
  -e APP_BASE_URL=http://localhost:8080 \
  -e SEED_ADMIN_LOGIN=admin \
  -e SEED_ADMIN_PASSWORD=change-me \
  network-king
```

The container defaults to:

- `PORT=8080`
- `DATABASE_URL=sqlite:////app/var/network_king.db`
- `LOCAL_MEDIA_ROOT=/app/var/uploads`

To persist the local SQLite database and uploaded images between runs, mount the app's `var` directory:

```bash
docker run \
  -p 8080:8080 \
  -e SECRET_KEY=change-me \
  -e APP_BASE_URL=http://localhost:8080 \
  -e SEED_ADMIN_LOGIN=admin \
  -e SEED_ADMIN_PASSWORD=change-me \
  -v "$(pwd)/var:/app/var" \
  network-king
```

For production, point `DATABASE_URL` at PostgreSQL and configure the rest of the environment variables as needed.

## Environment Variables

- `SECRET_KEY`: session signing key
- `DATABASE_URL`: SQLAlchemy database URL
- `APP_BASE_URL`: absolute app URL used in generated QR codes
- `SESSION_COOKIE_SECURE`: set to `true` in production
- `STORAGE_BACKEND`: `local` or `gcs`
- `LOCAL_MEDIA_ROOT`: local upload directory for development
- `GCS_BUCKET_NAME`: bucket name when `STORAGE_BACKEND=gcs`
- `SEED_ADMIN_LOGIN`: optional admin login to seed at startup
- `SEED_ADMIN_PASSWORD`: optional admin password to seed at startup
- `SEED_ADMIN_NAME`: optional seeded admin display name

## Test Suite

```bash
PYTHONPATH=. pytest -q
```

## Main Routes

- `/`: landing page with all events
- `/login`, `/logout`
- `/events/{slug}`: event board and leaderboard
- `/events/{slug}/scan`: browser scanner page with fallback input
- `/q/{qr_token}`: absolute QR target
- `/admin/events`
- `/admin/networkers`
- `/admin/events/{event_id}/characters`
