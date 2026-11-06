# LearnHub – Test Execution Report

## Status: the automated test suite has NOT been executed

The build environment had **no Django installation and package installation was disabled** (no network for `pip`/`npm`).
Consequently none of the following has been run, and no result below should be read as a pass:

* `python manage.py migrate`
* `python manage.py check`
* `python manage.py makemigrations --check` (the migrations were written by hand)
* `python manage.py test`
* starting the development server / browser checks

## What was written

| Test module | Tests | Covers |
|-------------|------:|--------|
| `accounts/tests.py` | 49 | UC1–UC4, session expiry, role access, status transitions |
| `courses/tests.py` | 47 | UC5, UC7, UC8, UC11, UC13, UC14, visibility, thumbnails |
| `materials/tests.py` | 28 | UC9, UC15, file permissions, file cleanup |
| `assignments/tests.py` | 42 | UC10, UC12, UC16, late/on-time, marks, DB constraints |
| `progress/tests.py` | 13 | progress formula, UC17, privacy between students |
| `dashboards/tests.py` | 8 | UC6 statistics, role dashboards |
| `core/tests.py` | 26 | file validators, CSRF, 28-URL authorization matrix, invalid IDs, path traversal, error pages, settings, backup/restore |
| **Total** | **213** | |

## What was actually verified in the build environment

| Check | Result |
|-------|--------|
| All 74 Python files parse (`ast.parse`) | passed |
| Every `{% url %}` name in templates and every `reverse()/redirect()` name in Python exists in a `urls.py` | passed (47 names) |
| Every view function referenced by a `urls.py` exists | passed |
| Every template `{% extends %}`/`{% include %}` target exists; `if/for/block/with` tags balanced in 35 templates | passed |
| No unused imports (custom AST scan) | passed |
| Tailwind build (`node tools/build_css.mjs`) with the installed `tailwindcss` 4.3.3 | passed – `static/css/app.css`, 27.8 KiB; component and responsive utilities spot-checked in the output |
| Backup → damage → restore round trip (`core/management/backup.py`) | passed (run directly with the standard library) |

These checks catch typos and wiring mistakes only. They do **not** prove the migrations match the models, that templates render, or that any test passes.

## Final implementation review (static inspection only)

Reviewed against the SRS and DD without being able to run Django. Nothing here is a test result.

| Area | Finding | Action |
|------|---------|--------|
| Account state machine (Fig-37) | Matches `ALLOWED_TRANSITIONS` / `REMOVABLE_STATUSES` (decision D-7) | D-7 marked confirmed |
| Submission state machine (Fig-39) and UC16 activity | Single submission, late flag from server time, failed upload creates nothing so retry works | D-1/D-17 annotated; 2 tests added (retry after rejected upload; deadline edit does not rewrite lateness) |
| Models vs. hand-written migrations (accounts) | Fields, choices, indexes and options correspond; `is_active` is a property so it has no column | none needed; real proof is `makemigrations --check` |
| Authentication / RBAC / file access | Role decorators, object-level 404/403, permission-checked file views, UUID names, content validation present and covered by the 28-URL matrix | none |
| Dashboards / progress | Formula matches D-3; cached `Enrollment.progress` is re-synced on every service-level change and when the progress page opens | documented |
| Test adequacy | Every UC1-UC17 has tests; gaps found were the two above | tests added |

Known soft spots a first run may expose: cosmetic `makemigrations --check` differences in the hand-written migrations (help_text/verbose_name), and test fixtures that were never executed.

## How to produce the real report (Windows, PowerShell or cmd)

```bat
cd path\to\learnhub
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test -v 2
python manage.py createsuperuser
python manage.py runserver
```

* `makemigrations --check --dry-run` must print "No changes detected". If it lists changes, run `python manage.py makemigrations`, then re-run the test suite.
* Backup check: `python manage.py backup_data --dest backups`
* CSS rebuild (optional, needs Node.js): `npm install` then `npm run build:css`
* PowerShell users: use `.venv\Scripts\Activate.ps1`; if scripts are blocked run `Set-ExecutionPolicy -Scope Process RemoteSigned` first.

Please paste any failures back; the tests were written against the code but never run, so a few fixes should be expected on the first run. After a green run, promote the matching rows in `docs/TRACEABILITY.md` from *Implemented* to *Tested*.

## Not testable by the automated suite (still open)

* Response time ≤ 2 s (SRS 23.1) and 100 concurrent users (23.3) – need a load test; SQLite serialises writes.
* 99 % availability (24.4) – operational.
* Chrome / Firefox / Edge and phone/tablet layouts (26.1–26.2) – need a manual browser pass.
* HTTPS (22.3) – depends on the deployment.
