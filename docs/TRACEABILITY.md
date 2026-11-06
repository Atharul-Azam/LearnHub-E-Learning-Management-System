# LearnHub – Requirements Traceability Matrix

Sources: SRS Table V (section 5) requirement IDs; DD use cases UC1–UC17 (activity/sequence diagrams) and state machines §6.1–6.4.

**Status legend** (per the project rules): *Not Started · In Progress · Implemented · Tested · Blocked.*
**Nothing is marked "Tested".** The test suite was written but **could not be executed in the build environment** (Django was not installed and package installation was disabled). Every row is therefore at most **Implemented**; after you run `python manage.py test` successfully, rows whose tests pass can be promoted to *Tested*. The test column names the test class that covers each row.

**Final review (static):** all 17 use cases and the four state machines (Fig-36..39 incl. account Fig-37 and submission Fig-39) were re-checked against the DD diagrams; no missing use case was found. Two tests were added to `SubmissionTests` (retry after rejected upload; lateness frozen at submission) – 213 tests in total. Still unverified by execution: migrations, template rendering, all tests, performance (23.1/23.3), availability (24.4), browsers (26.x), HTTPS (22.3). Windows commands: see `docs/TEST_REPORT.md`.

Abbreviations – models: `U`=accounts.User, `C`=courses.Course, `E`=courses.Enrollment, `M`=materials.LearningMaterial, `A`=assignments.Assignment, `S`=assignments.Submission, `MA`=progress.MaterialAccess.

## 1. Use cases

| UC | SRS ref. | Role | Model(s) | URL name(s) | View | Template(s) | Validation / security | Test class(es) | Status |
|----|----------|------|----------|-------------|------|-------------|-----------------------|----------------|--------|
| UC1 Register | 1.1–1.6 | Visitor | U | `accounts:register` | `accounts.views.register` | `accounts/register.html` | required fields, e-mail format + unique (case-insens.), password ≥8 letters+digits, hashed, CSRF, race-safe unique | `accounts.RegistrationTests` | Implemented |
| UC2 Login/Logout | 2.1–2.6, 21.5 | All | U, session | `accounts:login`, `accounts:logout` | `login_view`, `logout_view` | `accounts/login.html` | generic error; status messages only after correct password; only Active; POST-only logout; safe `next`; inactivity expiry | `accounts.LoginTests`, `SessionAndAccessTests` | Implemented |
| UC3 Approve/Reject teacher | 5.1–5.5 | Admin | U | `accounts:teacher_requests`, `…_detail`, `approve_teacher`, `reject_teacher` | `accounts.views_admin` | `admin_panel/teacher_request*.html`, `confirm/confirm.html` | admin only; confirmation page; state-machine guard; decision recorded (`decided_by/at`) | `accounts.AdminTeacherApprovalTests` | Implemented |
| UC4 Manage accounts | 4.1–4.5, 21.3 | Admin | U | `accounts:user_list/detail/activate_user/deactivate_user/remove_user` | `accounts.views_admin` | `admin_panel/user_*.html` | admin only; confirm before remove; transition table; teacher with courses protected; admins unmanageable | `accounts.AdminUserManagementTests` | Implemented |
| UC5 Manage courses (admin) | 6.1–6.5 | Admin | C | `courses:admin_list/detail/hide/publish/remove` | `courses.views_admin` | `admin_panel/course_*.html` | admin only; confirmation; hidden/removed not visible to students | `courses.AdminCourseTests` | Implemented |
| UC6 Statistics | 7.1–7.3 | Admin | U, C, E | `dashboards:admin` | `dashboards.views.platform_statistics` | `dashboards/admin.html` | computed by queries on every load | `dashboards.AdminStatisticsTests` | Implemented |
| UC7 Create course | 8.1, 9.1–9.4 | Teacher | C | `courses:teacher_create` | `courses.views_teacher` | `teacher/course_form.html` | required fields; thumbnail type/size/content (+Pillow); default image; owner set server-side; initial state Published | `courses.TeacherCourseTests`, `core.FileValidatorTests` | Implemented |
| UC8 Edit/Delete course | 8.2–8.5, 21.4 | Teacher | C | `courses:teacher_edit/delete/detail` | `courses.views_teacher` | `teacher/course_*.html` | ownership via `get_owned_course_or_404`; confirmation; cascade + file cleanup | `courses.TeacherCourseTests` | Implemented |
| UC9 Upload material | 10.1–10.4, 11.1 | Teacher | M | `materials:add/edit/delete` | `materials.views` | `materials/material_form.html` | owner only; type/size/content check; UUID file names; replace removes old file; remove deletes file | `materials.MaterialUploadTests` | Implemented |
| UC10 Publish assignment | 11.2–11.4 | Teacher | A | `assignments:teacher_add/edit/delete` | `assignments.views` | `assignments/assignment_form.html` | required fields; deadline; max marks ≥1; optional attachment validated; owner only | `assignments.AssignmentManagementTests` | Implemented |
| UC11 Enrolled students | 12.1–12.3 | Teacher | E, U | `courses:teacher_students` | `courses.views_teacher.teacher_students` | `teacher/enrolled_students.html` | only own courses; paginated | `courses.EnrolledStudentsTests` | Implemented |
| UC12 Review & marks | 13.1–13.3, 14.1–14.4 | Teacher | S | `assignments:teacher_detail/review/submission_file` | `assignments.views`, `services.save_review` | `assignments/teacher_assignment_detail.html`, `review_form.html` | owner only; 0 ≤ marks ≤ max (form + service + DB check); Reviewed only with marks; atomic | `assignments.ReviewTests` | Implemented |
| UC13 Browse/Search | 15.1–15.4, 9.4 | Student | C | `courses:browse` | `courses.views_student.browse` | `courses/browse.html` | published only; keyword AND-search over title/description/category; category filter; "No Courses Found"; paginated | `courses.BrowseSearchTests` | Implemented |
| UC14 Enroll | 16.1–16.4, 24.2 | Student | E | `courses:detail`, `courses:enroll` | `courses.views_student`, `services.enroll_student` | `courses/detail.html` | POST+CSRF; published only; unique constraint + service check | `courses.EnrollmentTests` | Implemented |
| UC15 Access material | 17.1–17.3, 18.1–18.4 | Student | M, MA, E | `courses:my_courses/open_course`, `materials:file` | `courses.views_student`, `materials.views.material_file` | `courses/my_courses.html`, `open_course.html` | enrollment + published check (403/404); publication order; records access; updates progress | `materials.MaterialAccessTests` | Implemented |
| UC16 Submit assignment | 19.1–19.4, 13.4 | Student | S | `assignments:student_detail`, `attachment` | `assignments.views.student_assignment`, `services.submit_assignment` | `assignments/student_assignment.html` | enrolled only; server-side timestamp/lateness; file validation; invalid upload changes nothing; one submission (D-1) | `assignments.SubmissionTests` | Implemented |
| UC17 Progress & marks | 20.1–20.4 | Student | E, MA, S | `progress:course_progress` | `progress.views.course_progress` | `progress/course_progress.html` | own data only; "Not Yet Reviewed" | `progress.ProgressAndMarksPageTests`, `ProgressCalculationTests` | Implemented |

## 2. Remaining functional requirements (dashboards)

| SRS | Requirement | Where | Test | Status |
|-----|-------------|-------|------|--------|
| 3.1 | Student dashboard: enrolled courses + browse shortcut | `dashboards.views.student_dashboard`, `dashboards/student.html` | `dashboards.RoleDashboardTests` | Implemented |
| 3.2 | Teacher dashboard: own courses + tools | `teacher_dashboard`, `dashboards/teacher.html` | `dashboards.RoleDashboardTests` | Implemented |
| 3.3 | Admin dashboard: management options + statistics | `admin_dashboard`, `dashboards/admin.html` | `dashboards.AdminStatisticsTests` | Implemented |
| 3.4 | No access to other roles' pages | `core.decorators.role_required` | `accounts.SessionAndAccessTests`, `core.DirectUrlAuthorizationTests` | Implemented |

## 3. Non-functional requirements

| SRS | Requirement | Implementation | Test / evidence | Status |
|-----|-------------|----------------|-----------------|--------|
| 21.1–21.4 | Authentication, RBAC, ownership, enrollment checks | `role_required`, `get_owned_course_or_404`, `get_student_enrollment`, per-file permission checks | `core.DirectUrlAuthorizationTests` (matrix of 28 URLs × 5 visitor kinds + anonymous) | Implemented |
| 21.5 | Configurable inactivity timeout | `SESSION_COOKIE_AGE` (env) + `SESSION_SAVE_EVERY_REQUEST` | `accounts.SessionAndAccessTests` | Implemented |
| 22.1 | Hashed passwords | Django `set_password` | `RegistrationTests` | Implemented |
| 22.2 | ≥8 chars, letters + numbers | `AUTH_PASSWORD_VALIDATORS` | `RegistrationTests.test_password_rules` | Implemented |
| 22.3 | HTTPS in deployment | `config/settings/prod.py` flags + README guidance. **No HTTPS has been configured or verified.** | – | Implemented (configuration only) |
| 22.4 | Input validation/sanitisation | Django forms, ORM (no raw SQL), template auto-escaping | form tests in each app | Implemented |
| 22.5 | File type/size checks before storing | `core/validators.py` | `core.FileValidatorTests` + upload tests | Implemented |
| 22.6 | Security testing | `core.CsrfTests`, `DirectUrlAuthorizationTests`, `ErrorHandlingTests` | – | Implemented (tests unexecuted) |
| 23.1 | ≤ 2 s response | indexed queries, `select_related`, annotations | **not measured** | Not verified |
| 23.2 | Pagination | `core.pagination.paginate` on all long lists | `BrowseSearchTests.test_pagination`, `AssignmentManagementTests.test_pagination_of_submissions` | Implemented |
| 23.3 | 100 concurrent users | – | **needs load testing; SQLite write concurrency is a known limit** | Not verified |
| 24.1 | Regular backups | `manage.py backup_data` (DB snapshot via SQLite backup API + media archive); scheduling documented in README | `core.BackupRestoreTests`; round trip also executed manually in the build environment | Implemented (round trip verified, scheduling is the operator's job) |
| 24.2 | Data consistency | DB constraints (unique enrollment/submission/access, progress ≤ 100, marks ≥ 0, reviewed ⇒ marks), `transaction.atomic` | `EnrollmentTests`, `SubmissionTests`, `ReviewTests.test_database_constraints` | Implemented |
| 24.3 | Graceful errors | 403/404/500/CSRF templates, DB-error handling in views, logging | `ErrorHandlingTests` | Implemented |
| 24.4 | 99 % availability | operational target – cannot be verified in code | – | Not verified |
| 24.5 | Documented recovery | README "Backup and recovery" + `backup_data --restore` | `BackupRestoreTests` | Implemented |
| 25.1–25.4 | Consistent, clear, responsive UI | shared `base.html`, Tailwind responsive utilities, messages on every action | **not checked in a browser** | Implemented (visual check pending) |
| 26.1–26.2 | Chrome/Firefox/Edge; all screen sizes | standard HTML/CSS (`has-[:checked]` used for the radio highlight needs a current browser) | **not checked in browsers** | Not verified |
| 27.1 | Separate layers | templates / views+forms+services / models+SQLite+media | structure | Implemented |
| 27.2 | Documented interfaces | this document, README URL map, docstrings | – | Implemented |
| 27.3 | Version control + docs | `.gitignore`, README, docs/ (repository not initialised) | – | Implemented |
| 27.4 | Extensible modules | one Django app per concern, business rules in `services.py` | – | Implemented |

## 4. State machines (DD §6)

| DD | State machine | Enforced in | Test | Status |
|----|---------------|-------------|------|--------|
| 6.1 | User account | `accounts/services.py::ALLOWED_TRANSITIONS`; only Active can authenticate (`User.is_active`) | `AdminTeacherApprovalTests`, `AdminUserManagementTests`, `LoginTests`, `UserModelTests` | Implemented |
| 6.2 | Authentication session | Django sessions, inactivity expiry | `SessionAndAccessTests`, `LoginTests` | Implemented |
| 6.3 | Submission | `assignments/services.py` + model `status` + DB constraints | `SubmissionTests`, `ReviewTests` | Implemented |
| 6.4 | Course visibility | `courses/services.py::set_visibility` / `remove_course` | `AdminCourseTests`, `TeacherCourseTests` | Implemented |

## 5. Data model (DD Fig-19 → Django)

| DD class | Django model | Notes |
|----------|--------------|-------|
| Administrator / Teacher / Student | `accounts.User` (`role`, `status`) | single table; DD's three subclasses become roles |
| Course | `courses.Course` | FK teacher (PROTECT); `visibility`; indexes on (visibility, category) and (teacher, created_at) |
| Enrollment | `courses.Enrollment` | unique (student, course); `progress` 0–100 |
| LearningMaterial | `materials.LearningMaterial` | FK course (CASCADE) |
| Assignment | `assignments.Assignment` | FK course (CASCADE); optional attachment |
| Submission | `assignments.Submission` | unique (assignment, student); `is_late`, `marks`, `feedback`, `reviewed` |
| (progress tracking, SRS 20.2) | `progress.MaterialAccess` | unique (student, material) |
