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
| `accounts/test_verification.py` | 29 | e-mail verification (valid / reused / tampered / expired / resend / rate limit), Student & Teacher IDs (uniqueness, DB constraints, retry) |
| `accounts/test_profile.py` | 35 | profile, picture validation and cleanup, settings, theme/font persistence, password change, sign-out-others, account deletion policy |
| `courses/tests.py` | 47 | UC5, UC7, UC8, UC11, UC13, UC14, visibility, thumbnails |
| `courses/test_private.py` | 58 | public/private visibility, invitation tokens, access requests (duplicate, approve, reject, revoke), sharing, favourites, search/filter/sort, recently viewed |
| `materials/tests.py` | 28 | UC9, UC15, file permissions, file cleanup |
| `assignments/tests.py` | 42 | UC10, UC12, UC16, late/on-time, marks, DB constraints |
| `progress/tests.py` | 13 | progress formula, UC17, privacy between students |
| `notifications/tests.py` | 20 | dedupe, preferences, read / read-all, ownership, deadline reminders, event hooks |
| `community/tests.py` | 26 | announcements, discussion access (members only), edit/delete/moderation permissions, XSS escaping |
| `dashboards/tests.py` | 8 | UC6 statistics, role dashboards |
| `dashboards/test_stats.py` | 26 | student & teacher dashboards, analytics correctness and scoping, navigation indicators |
| `core/test_seed_demo.py` | 22 | demo seeder: sizes, verified accounts, unique IDs, idempotency, real users untouched, no e-mail, production refusal, logins |
| `core/tests.py` | 30 | file validators, CSRF, URL authorization matrix (now 47 URLs x 5 visitors + anonymous), invalid IDs, path traversal, error pages, settings, backup/restore, CSRF/method rules of new endpoints |
| **Total** | **434** | (counted from the source with `grep -c "    def test_"`; was 211 before the advanced-feature release) |

## What was actually verified in the build environment

| Check | Result |
|-------|--------|
| All 91 Python files parse (re-run after the advanced-feature release) (`ast.parse`) | passed |
| Every `{% url %}` name in templates and every `reverse()/redirect()` name in Python exists in a `urls.py` | passed (80 names) |
| Every view function referenced by a `urls.py` exists | passed |
| Every template `{% extends %}`/`{% include %}` target exists; `if/for/block/with` tags balanced in all templates | passed |
| No unused imports, no undefined names (custom AST scans) | passed |
| Tailwind build (`node tools/build_css.mjs`) with the installed `tailwindcss` 4.3.3 | passed – `static/css/app.css`, 39 KiB (rebuilt after the redesign); component and responsive utilities spot-checked in the output |
| Backup → damage → restore round trip (`core/management/backup.py`) | passed (run directly with the standard library) |

These checks catch typos and wiring mistakes only. They do **not** prove the migrations match the models, that templates render, or that any test passes.

## Defect found after delivery (teacher dashboard HTTP 500) - fixed, fix not yet executed here

* Symptom (reported by the user, who could run Django): `OperationalError: misuse of aggregate function COUNT()` in `dashboards/stats.py::teacher_course_performance`, `/dashboard/teacher/` returned 500.
* Cause: the aggregate aliases `reviewed` / `pending` were annotated after `.values()`, and `reviewed` is also a `Submission` field. Django skips its alias/field conflict check after `.values()`, so `Q(reviewed=False)` inside the `pending` aggregate resolved to the *aggregate* `reviewed`, producing `COUNT(..) FILTER (WHERE COUNT(..) ...)`. SQLite rejects an aggregate inside an aggregate's filter. The same SQL shape was reproduced directly in SQLite (error reproduced; renamed-alias version returns the right rows). Django itself could not be run here, so the generated SQL was inferred, not printed.
* Fix: aliases renamed (`submissions_count`, `reviewed_count`, `pending_count`), `.order_by()` added; output dict keys unchanged. 7 regression tests added (`CoursePerformanceQueryTests`). Not executed here.
* Lesson: the original analytics tests already called this query and would have caught it; the suite had simply never been run.

## Mandatory checklist of the advanced-feature request (30 items)

"Written" means an automated test exists in the repository. **Nothing below has been run**, so no row says "passed".

| # | Item | Test module(s) | Status |
|--:|------|----------------|--------|
| 1-3 | Verification works; unverified cannot log in; verified student can | `accounts/test_verification.py` | Written, not run |
| 4 | Teacher approval workflow intact | `test_verification.py::test_teacher_needs_both…`, `accounts/tests.py` | Written, not run |
| 5 | Student/Teacher IDs unique | `test_verification.py::PublicIdTests` | Written, not run |
| 6-7 | Picture upload/update, profile editing | `accounts/test_profile.py::ProfileTests` | Written, not run |
| 8-9 | Settings persist, theme switching (server side: stored and rendered as `data-theme`) | `test_profile.py::SettingsTests` | Written, not run. The visual dark theme itself needs a browser check |
| 10 | Logout | `test_profile.py` | Written, not run |
| 11 | Account deletion safe | `test_profile.py::AccountDeletionTests` | Written, not run |
| 12-13, 17 | Public visible; private hidden; no URL access | `courses/test_private.py::VisibilityTests`, `core/tests.py` | Written, not run |
| 14-16 | Invitation links, access requests, approve/reject | `test_private.py::InvitationAndRequestTests`, `InviteManagementTests` | Written, not run |
| 18 | Sharing | `test_private.py::StudentSharingTests`; the copy-to-clipboard button is JavaScript and is **not** covered | Partly written, not run |
| 19-20 | Dashboards correct | `dashboards/test_stats.py` | Written, not run |
| 21 | Search / filter | `test_private.py::DiscoveryTests` | Written, not run |
| 22 | Progress updates | `progress/tests.py` (unchanged) | Written, not run |
| 23 | Notifications | `notifications/tests.py` | Written, not run |
| 24 | Discussion permissions | `community/tests.py` | Written, not run |
| 25 | Favourites | `test_private.py::FavouriteTests` | Written, not run |
| 26 | Teacher analytics correct and scoped | `dashboards/test_stats.py` | Written, not run |
| 27 | Navigation indicators (server-computed) | `dashboards/test_stats.py::NavigationTests` | Written, not run |
| 28 | **Responsive layouts** | none – needs a real browser at desktop/tablet/phone widths | **Not tested** |
| 29-30 | Existing assignments, submissions, marks, enrollment | existing modules, adjusted only where behaviour changed | Written, not run |

Existing tests that had to change because behaviour changed (e-mail verification): `accounts/tests.py` (teacher registration message, unverified flag), `core/factories.py` (test users are created verified).

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
