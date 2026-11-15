LearnHub – E-Learning Management System

Django + Django templates + Tailwind CSS + vanilla JavaScript + SQLite + local media storage, as specified in the Detailed Design Document.
Roles: **Administrator**, **Teacher**, **Student**. All 17 use cases (UC1–UC17) are implemented.

**Advanced-feature release** (requested after the SRS/DD – see `docs/DECISIONS.md` D-19…D-34): e-mail verification, Student/Teacher IDs, profiles and settings (theme, font, notification preferences, password, account deletion), public and private courses with invitation links and teacher approval, favourites, sharing, in-app notifications, announcements, course discussion, redesigned dashboards, teacher analytics, active-tab navigation and a dark theme.

> **Verification status – read first.** The code and the 434 automated tests were written in an environment where Django could not be installed, so **migrations, `manage.py check`, the test suite and the running application have not been executed yet.** See [docs/TEST_REPORT.md](docs/TEST_REPORT.md) for exactly what was and was not verified, and run the commands under *Verify the build* first.

Documents: [docs/TRACEABILITY.md](docs/TRACEABILITY.md) (requirements matrix) · [docs/DECISIONS.md](docs/DECISIONS.md) (conflicts, ambiguities, decisions) · [docs/TEST_REPORT.md](docs/TEST_REPORT.md).

## 1. Prerequisites

* Python 3.10 – 3.13
* Node.js 18+ **only if you want to change the styles** (the compiled `static/css/app.css` is already included)

## 2. Setup

```bash
# from the project folder (the one containing manage.py)
python -m venv .venv

# activate
source .venv/bin/activate          # Linux / macOS
.venv\Scripts\activate             # Windows (cmd / PowerShell)

pip install -r requirements.txt

cp .env.example .env               # Windows: copy .env.example .env   (edit values if needed)

python manage.py migrate           # creates db.sqlite3
python manage.py createsuperuser   # creates the Administrator (asks for e-mail, name, password)
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. Log in with the administrator you just created. There is **no demo data**: students register themselves, teachers register and wait for approval (Admin → *Teacher Requests*).

The password must have at least 8 characters with letters and numbers (this also applies to `createsuperuser`).

### E-mail verification (new accounts must verify)

* Development: with no `EMAIL_HOST` in `.env`, the verification e-mail is **printed in the terminal running `runserver`** – copy the link from there.
* Real e-mail: set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` and `SITE_URL` in `.env` (never commit it).
* No e-mail available: `python manage.py verify_user someone@example.com`.
* Accounts that existed before this release are marked verified by the migration; `createsuperuser` accounts are verified.
* Existing database: run `python manage.py migrate` (it adds the new columns and gives existing students/approved teachers their IDs). Back up `db.sqlite3` first: `python manage.py backup_data`.

## 3. Verify the build

```bash
python manage.py check
python manage.py makemigrations --check --dry-run   # expected: "No changes detected"
python manage.py test -v 2
```

## 3a. Demo data (optional, development only)

```bat
python manage.py seed_demo_data
```

Creates 15 approved teachers, 55 students, an administrator, 17 courses (12 public, 5 private) and realistic activity, all as already-verified accounts (nothing is e-mailed and normal registration is unchanged). Logins go to `DEMO_CREDENTIALS.local.md` (git-ignored). Safe to re-run; never deletes or alters real users. Details, safety rules and limits: [docs/DEMO_DATA.md](docs/DEMO_DATA.md). **Not yet executed** by the author (see the status note at the top).

## 4. Tailwind CSS

Sources: `static_src/input.css` (+ the classes used in `templates/`, `static/js/` and the `forms.py` widgets). Output: `static/css/app.css`.

```bash
npm install              # installs only the tailwindcss package
npm run build:css        # one-off build
npm run watch:css        # rebuild on change
```

The build script (`tools/build_css.mjs`) uses the `tailwindcss` v4 compile API directly, so no native CLI binary is needed. No CDN is used at run time.

## 5. Project structure

```
config/            settings (base / dev / prod), root urls, wsgi
core/              decorators (role checks), upload validators, safe file storage + serving, pagination, backup tool
accounts/          custom User model, registration/login, e-mail verification, IDs, profile/settings, admin: teacher approval + account management  (UC1-UC4)
courses/           Course, Enrollment; admin course management, teacher courses, student browse/enroll   (UC5,7,8,11,13,14)
materials/         LearningMaterial; upload/replace/remove, controlled viewing/download                   (UC9, UC15)
assignments/       Assignment, Submission; publish, submit, review, marks/feedback                        (UC10, UC12, UC16)
progress/          MaterialAccess, progress calculation, progress/marks page                              (UC15, UC17)
dashboards/        three role dashboards + platform statistics                                            (UC6)
templates/         Django templates      static/  compiled CSS, JS, default thumbnail      docs/  documents
```

Business rules live in `*/services.py`; views are thin; forms hold validation. Role checks are server-side (`core/decorators.py`), object ownership/enrollment checks are in the views/`courses/access.py`.

### URL map (summary)

| Area | URLs |
|------|------|
| Public | `/accounts/register/`, `/accounts/login/`, `/accounts/verify/<uid>/<token>/`, `/accounts/resend-verification/`, `POST /accounts/logout/` |
| Any signed-in user | `/profile/`, `/settings/…`, `/notifications/` |
| Admin | `/dashboard/admin/`, `/manage/teacher-requests/`, `/manage/users/`, `/manage/courses/` |
| Teacher | `/dashboard/teacher/`, `/dashboard/teacher/analytics/`, `/teacher/requests/`, `/teacher/courses/…` (incl. `/share/`, `/requests/`, `/community/`), `/teacher/materials/…`, `/teacher/assignments/…`, `/teacher/submissions/<id>/` |
| Student | `/dashboard/student/`, `/courses/`, `/favourites/`, `/join/<token>/`, `/my-courses/<id>/`, `/my-courses/<id>/progress/`, `/my-courses/<id>/community/`, `/assignments/<id>/` |
| Files (permission-checked) | `/files/avatars/<id>/`, `/files/thumbnails/<id>/`, `/files/materials/<id>/`, `/files/assignments/<id>/`, `/files/submissions/<id>/` (add `?download=1` to force a download) |

## 6. Configuration (`.env`)

See `.env.example`. Key settings: `SECRET_KEY`, `ALLOWED_HOSTS`, `DEBUG` (dev), `SESSION_INACTIVITY_TIMEOUT_SECONDS` (default 1800), `MAX_*_MB` upload limits, `PAGE_SIZE`, `DB_PATH`, `MEDIA_ROOT`. Allowed file types are in `UPLOAD_RULES` in `config/settings/base.py`.

`manage.py` uses `config.settings.dev`; `wsgi.py` uses `config.settings.prod`. Override with `DJANGO_SETTINGS_MODULE`.

## 7. Deployment (outline – not performed or verified)

1. Set environment variables: `DJANGO_SETTINGS_MODULE=config.settings.prod`, a long random `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and `DB_PATH` / `MEDIA_ROOT` on persistent storage **outside the source folder**.
   Generate a key: `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`.
2. `python manage.py migrate` and `python manage.py collectstatic --noinput`.
3. Run with a WSGI server (for example `gunicorn config.wsgi:application`) behind a web server such as Nginx/Apache that:
   * terminates **HTTPS** (certificate from your CA/Let's Encrypt) and redirects HTTP to HTTPS,
   * serves `/static/` from `STATIC_ROOT` (`staticfiles/`),
   * does **not** expose `MEDIA_ROOT` – uploaded files must only be reachable through the Django file views,
   * sets `X-Forwarded-Proto` (then set `BEHIND_PROXY=True`).
4. `prod.py` turns on secure cookies, HTTP→HTTPS redirect and HSTS (`USE_HTTPS=True`, the default). Set `USE_HTTPS=False` only for a trial over plain HTTP.
5. Run `python manage.py check --deploy` and fix what it reports.

**Limits to know:** SQLite allows one writer at a time. The SRS target of 100 concurrent users has not been load-tested; if it proves too slow, that is a finding to report – the database was not replaced because the DD requires SQLite.

Free hosting walkthrough (PythonAnywhere, step by step, untested on the live service): [docs/DEPLOY_PYTHONANYWHERE.md](docs/DEPLOY_PYTHONANYWHERE.md).

## 8. Backup and recovery

Backup (safe while the site runs; DB snapshot uses SQLite's online backup API):

```bash
python manage.py backup_data                 # writes backups/learnhub-backup-<timestamp>.tar.gz (database + media)
python manage.py backup_data --dest /mnt/backups
```

Schedule it (SRS 24.1), e.g. nightly with cron: `0 2 * * * cd /srv/learnhub && .venv/bin/python manage.py backup_data --dest /mnt/backups`
(Windows: Task Scheduler running the same command). Keep copies off the server and delete old archives according to your retention policy.

Recovery (SRS 24.5):

1. Stop the web server / WSGI process.
2. `python manage.py backup_data --restore /mnt/backups/learnhub-backup-YYYYMMDD-HHMMSS.tar.gz`
   (the current database and media folder are kept as `*.before-restore`).
3. `python manage.py migrate` (only needed if the code is newer than the backup), then start the server.
4. Log in and spot-check courses, a material download and a submission.

Test your restore procedure on a copy before you need it.

## 9. Known limitations

* Tests, migrations, system check and the running app are **unverified** (see top of this file).
* No performance, concurrency, availability or cross-browser verification (SRS 23.1, 23.3, 24.4, 26.1).
* The advanced-feature release has the same verification status as everything else: **not executed**. Responsive layout, dark-theme contrast and the copy-to-clipboard button were never checked in a browser.
* In-app notifications only (no e-mail notifications); deadline reminders are created when a student opens the dashboard or notification list.
* Django Admin is not enabled (D-34).
* Single submission per student per assignment (documented ambiguity D-1 – confirm with the client).
* Out of scope per the SRS (not implemented): profile management, quizzes, notifications, discussion forums, certificates, advanced analytics.
* Hand-written migrations: if `makemigrations --check` reports changes, run `makemigrations` and commit the result.
