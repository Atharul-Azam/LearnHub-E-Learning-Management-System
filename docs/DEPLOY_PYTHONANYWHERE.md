# Deploying LearnHub free on PythonAnywhere

**Status: NOT deployed by Claude.** Deployment needs your own PythonAnywhere login, which Claude cannot create or use. Nothing below has been tested on the live service; follow it and report any error.

## Why PythonAnywhere (and not Render)

| | PythonAnywhere free | Render free |
|---|---|---|
| Django | yes | yes |
| Uploaded files survive restarts | **yes** (normal disk) | **no** – filesystem is wiped on every redeploy/restart/spin-down; persistent disks are paid |
| SQLite | works (normal disk) | would be wiped; needs external DB |
| Free database expiry | none (SQLite is a file) | free Postgres **expires after 30 days**, deleted after a 14-day grace period |
| Sleeps when idle | no sleeping of the web app | spins down after 15 minutes, ~1 minute to wake |
| Code changes needed | none | storage + database rewrite |

LearnHub keeps files and data on local disk by design (SQLite + local media), so PythonAnywhere is the only free option that works **without** changing storage. Sources: [PythonAnywhere free accounts](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/), [Render free tier](https://render.com/docs/free).

## Free-tier limits you must accept (from the vendor pages, checked 2026-11-07)

* One web app, one worker.
* **The web app expires after one month** unless you log in and press the extend button on the *Web* tab. Set a calendar reminder. (The vendor page does not give further details; confirm the exact rule on your Web tab.)
* 512 MiB total disk (code + database + all uploads). Keep demo uploads small; lower `MAX_MATERIAL_MB` if needed.
* Daily CPU allowance (100 CPU-seconds on the vendor page) – fine for a demo, not for many users.
* URL is `https://<username>.pythonanywhere.com` with HTTPS provided. Not verified here: maximum request/upload size and outbound internet access (not needed by LearnHub).
* Not load-tested: SRS 23.1/23.3 (2 s, 100 users) are not met-or-unmet evidence on this tier.

## Steps (browser + the PythonAnywhere Bash console)

1. Sign up for a free **Beginner** account at pythonanywhere.com (no card). Remember your username (`USER` below).
2. **Upload the project**: *Files* tab → upload `learnhub.zip` into your home folder, then open a **Bash console**:
   ```bash
   cd ~ && unzip learnhub.zip && cd learnhub
   ```
   (If you use GitHub instead: `git clone <your repo url>`; the repo must not contain `.env` or `db.sqlite3`.)
3. **Virtualenv** (pick a Python version PythonAnywhere offers, 3.10+; example 3.12):
   ```bash
   mkvirtualenv learnhub --python=python3.12
   pip install -r requirements.txt
   ```
4. **Create `.env`** in `~/learnhub` (never commit it). Generate a key first:
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
   nano .env
   ```
   Contents (replace USER and the key):
   ```
   SECRET_KEY=<paste the generated key>
   ALLOWED_HOSTS=USER.pythonanywhere.com
   CSRF_TRUSTED_ORIGINS=https://USER.pythonanywhere.com
   USE_HTTPS=True
   BEHIND_PROXY=True
   TIME_ZONE=Asia/Dhaka
   DB_PATH=/home/USER/learnhub_data/db.sqlite3
   MEDIA_ROOT=/home/USER/learnhub_data/media
   ```
   Keeping data in `~/learnhub_data` (outside the code folder) means re-uploading new code never overwrites your database or files.
5. **Initialise** (`manage.py` defaults to development settings, so select production first in every new console):
   ```bash
   export DJANGO_SETTINGS_MODULE=config.settings.prod
   mkdir -p ~/learnhub_data/media
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py check --deploy
   python manage.py createsuperuser        # your Administrator (you type the password; never share it)
   ```
6. **Web tab → Add a new web app → Manual configuration** → same Python version. Then set:
   * *Source code*: `/home/USER/learnhub`
   * *Virtualenv*: `/home/USER/.virtualenvs/learnhub`
   * *Static files*: URL `/static/` → Directory `/home/USER/learnhub/staticfiles`
   * **Do not add a `/media/` mapping.** Uploads must only be served through LearnHub's permission-checked views.
7. **WSGI file** (link on the Web tab): delete its contents and put:
   ```python
   import os, sys
   path = "/home/USER/learnhub"
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
   (`config/settings/base.py` reads `.env` from the project folder, so the variables from step 4 are picked up.)
8. Press **Reload**, open `https://USER.pythonanywhere.com/`.

## E-mail on the free tier (important)

New accounts must verify their e-mail address. The free PythonAnywhere plan restricts outbound connections to an allow-list of sites, so an ordinary SMTP server may be unreachable (not verified here). If a verification e-mail cannot be sent:

* register normally, then verify the person yourself in a Bash console: `python manage.py verify_user someone@example.com` (with `DJANGO_SETTINGS_MODULE` exported as in step 5);
* or configure an SMTP provider that your plan can reach (`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` in `.env`; see `.env.example`).

Also set `SITE_URL=https://USER.pythonanywhere.com` in `.env`.

## Check it works (do this yourself; report any failure)

1. Home/login/register pages load with styling (if unstyled: the static mapping in step 6 is wrong).
2. Log in as the administrator you created.
3. Register a **teacher** (use a throwaway password) → approve under *Teacher Requests*.
4. As teacher: create a course, upload a small PDF material, add an assignment.
5. Register a **student** → enrol → open material → submit a file → as teacher review with marks → student sees marks and progress.
6. Reload the web app, confirm the data and uploaded files are still there.
7. Privacy: copy a file URL (`/files/submissions/<id>/`), open it in a private window → must redirect to login/deny.

## Updating the code later

Upload the new zip (or `git pull`), then in the console with the virtualenv active and `export DJANGO_SETTINGS_MODULE=config.settings.prod` set: `pip install -r requirements.txt`, `python manage.py migrate`, `python manage.py collectstatic --noinput`, and press **Reload**. Data in `~/learnhub_data` is untouched.

## Backup and recovery

```bash
cd ~/learnhub && export DJANGO_SETTINGS_MODULE=config.settings.prod && python manage.py backup_data --dest ~/backups    # database + media, safe while running
```
Download the `.tar.gz` from the *Files* tab regularly (the free disk is the only copy otherwise). Restore: `python manage.py backup_data --restore ~/backups/<file>.tar.gz`, then Reload.

## Moving existing local data

Migrations create empty tables; they do **not** copy your local records. To keep your local data: run `python manage.py backup_data` on your PC, upload that archive, and restore it as above (after step 5's `migrate`, before creating a duplicate admin). Keep your original `db.sqlite3` untouched as a second backup.
