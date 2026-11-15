"""Create (or top up) a complete demo environment:  python manage.py seed_demo_data

Safety rules (see docs/DEMO_DATA.md)
* Only ever touches accounts whose e-mail ends in ``@demo.learnhub.test`` and the courses
  those teachers own. Real users, their passwords and their data are never read or changed.
* Never flushes, resets or deletes anything. Running it again adds only what is missing.
* Demo accounts are created *already verified* by setting the flag directly. No e-mail is
  sent, and the normal registration / verification workflow is not modified in any way.
* Refuses to run when DEBUG is off (production) unless --allow-production is given.
* The demo password is never stored in the source code: it is generated on the first run and
  written to DEMO_CREDENTIALS.local.md (git-ignored).
"""
import os
import re
import secrets
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from accounts.identifiers import ensure_public_id
from accounts.models import User
from assignments.models import Assignment, Submission
from assignments.services import notify_new_assignment, save_review
from community.models import Announcement, Post
from community.services import notify_announcement, notify_post
from core import demo_data as plan
from core.demo_files import make_avatar, make_pdf
from core.services import BusinessRuleError
from courses import private
from courses.models import Course, CourseAccessRequest, Enrollment, Favourite
from courses.services import enroll_student
from materials.models import LearningMaterial
from notifications.models import Notification
from notifications.services import notify
from progress.models import MaterialAccess
from progress.services import compute_progress, sync_course_progress

CREDENTIALS_FILE = Path(settings.BASE_DIR) / "DEMO_CREDENTIALS.local.md"
PASSWORD_RE = re.compile(r"Password:\s*`([^`]+)`")
Cat = Notification.Category


class Command(BaseCommand):
    help = "Create realistic demo teachers, students, courses and activity (safe to run repeatedly)."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Demo password to use for NEW demo accounts (default: generated once).")
        parser.add_argument("--reset-demo-passwords", action="store_true",
                            help="Also set the demo password on EXISTING demo accounts (never on other accounts).")
        parser.add_argument("--allow-production", action="store_true",
                            help="Allow running when DEBUG is off (e.g. a hosted demo). Demo passwords then protect real data.")
        parser.add_argument("--refresh-covers", action="store_true",
                            help="Remove the image thumbnails of DEMO courses so the generated category covers show "
                                 "(older seeds created initials-only images). Other courses are never touched.")
        parser.add_argument("--check-only", action="store_true", help="Only verify the existing demo data; change nothing.")
        parser.add_argument("--credentials-file", default=str(CREDENTIALS_FILE), help="Where to write the local credentials note.")

    # ------------------------------------------------------------------ main
    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["allow_production"]:
            raise CommandError(
                "Refusing to create demo accounts while DEBUG is off (production settings). "
                "Run with the development settings, or pass --allow-production if you really want a hosted demo."
            )
        if opts["check_only"]:
            self._report(self.verify())
            return

        self.credentials_path = Path(opts["credentials_file"])
        self.password = self._resolve_password(opts["password"])
        self.reset_passwords = opts["reset_demo_passwords"]
        self.refresh_covers = opts["refresh_covers"]
        self.now = timezone.now()
        self.stats = {"users_created": 0, "users_existing": 0}
        self.new_future_assignments = []

        with transaction.atomic():
            self.admin = self._seed_admin()
            self.teachers = self._seed_teachers()
            self.students = self._seed_students()
            self.courses = self._seed_courses()
            self._seed_public_enrollments()
            self._seed_private_requests()
            for assignment in self.new_future_assignments:
                notify_new_assignment(assignment)
            self._seed_activity()
            self._seed_announcements_and_discussion()
            self._seed_favourites()
            self._seed_notifications()

        self._write_credentials()
        self.stdout.write(self.style.SUCCESS(
            f"Seed finished: {self.stats['users_created']} accounts created, {self.stats['users_existing']} already existed."))
        self._report(self.verify())
        self.stdout.write(f"Login details: {self.credentials_path}  (local file, do not share or commit)")
        self.stdout.write(f"Demo password: {self.password}")

    # ------------------------------------------------------------------ helpers
    def _resolve_password(self, given):
        """--password, then $DEMO_PASSWORD, then the existing local credentials file, else a new random one."""
        if given:
            return given
        if os.environ.get("DEMO_PASSWORD"):
            return os.environ["DEMO_PASSWORD"]
        try:
            match = PASSWORD_RE.search(self.credentials_path.read_text(encoding="utf-8"))
        except OSError:
            match = None
        return match.group(1) if match else "Demo-" + secrets.token_urlsafe(9)

    def _user(self, email, name, role, **extra):
        """Get or create a demo account. Existing accounts keep their password and data."""
        user = User.objects.filter(email=email).first()
        if user is None:
            if role == User.Role.ADMIN:
                user = User.objects.create_superuser(email=email, name=name, password=self.password)
            else:
                # email_verified=True is set directly: demo accounts need no mail round-trip.
                user = User.objects.create_user(
                    email=email, name=name, password=self.password, role=role, email_verified=True, **extra)
            self.stats["users_created"] += 1
            return user, True
        self.stats["users_existing"] += 1
        if user.role != role:
            self.stderr.write(self.style.WARNING(f"{email} exists with another role; left untouched."))
            return user, False
        changed = []
        if not user.email_verified:
            user.email_verified = True
            changed.append("email_verified")
        if changed:
            user.save(update_fields=changed)
        if user.status == User.Status.ACTIVE:
            ensure_public_id(user)
        if self.reset_passwords:
            user.set_password(self.password)
            user.save(update_fields=["password"])
        return user, False

    def _backdate(self, queryset, when):
        queryset.update(created_at=when)

    # ------------------------------------------------------------------ people
    def _seed_admin(self):
        admin, _ = self._user(plan.ADMIN_EMAIL, "Demo Administrator", User.Role.ADMIN)
        return admin

    def _seed_teachers(self):
        teachers = {}
        for number, (name, expertise, bio) in enumerate(plan.TEACHERS, start=1):
            teacher, created = self._user(
                plan.teacher_email(number), name, User.Role.TEACHER, status=User.Status.ACTIVE,
                expertise=expertise, bio=bio, decided_at=self.now - timedelta(days=90), decided_by=self.admin)
            if created and not teacher.profile_picture:
                colour = list(plan.CATEGORY_COLOURS.values())[number % len(plan.CATEGORY_COLOURS)]
                teacher.profile_picture.save("avatar.png", ContentFile(make_avatar(name, colour)), save=False)
                teacher.save(update_fields=["profile_picture"])
            teachers[number] = teacher
        for number, (name, expertise, bio) in enumerate(plan.PENDING_TEACHERS, start=1):
            self._user(plan.pending_teacher_email(number), name, User.Role.TEACHER, status=User.Status.PENDING,
                       expertise=expertise, bio=bio)
        return teachers

    def _seed_students(self):
        students = []
        for i in range(plan.STUDENT_COUNT):
            student, _ = self._user(
                plan.student_email(i + 1), plan.student_name(i), User.Role.STUDENT,
                theme=plan.student_theme(i), font=plan.student_font(i),
                bio="Demo student account." if i % 4 == 0 else "")
            students.append(student)
        return students

    # ------------------------------------------------------------------ courses
    def _seed_courses(self):
        courses = {}
        for idx, (title, category, teacher_no, access, visibility, description, topics) in enumerate(plan.COURSES):
            teacher = self.teachers[teacher_no]
            course = Course.objects.filter(teacher=teacher, title=title).first()
            created = course is None
            if created:
                course = Course.objects.create(
                    teacher=teacher, title=title, category=category, description=description,
                    access=access, visibility=visibility, created_at=self.now - timedelta(days=60 - idx))
            # No thumbnail is generated: the interface draws a category cover for courses without one.
            if self.refresh_covers and course.thumbnail:
                course.thumbnail.delete(save=False)
                course.save(update_fields=["thumbnail", "updated_at"])
            if course.is_private:
                if created:
                    private.generate_invite(course, plan.INVITE_EXPIRY.get(idx, "never"))
                else:
                    private.sync_access(course)
            courses[idx] = course
            self._seed_materials(course, topics)
            self._seed_assignments(idx, course)
        return courses

    def _seed_materials(self, course, topics):
        for j, topic in enumerate(topics):
            title = f"{topic} - lecture notes"
            if LearningMaterial.objects.filter(course=course, title=title).exists():
                continue
            material = LearningMaterial(course=course, title=title, original_name=f"{slugify(topic)}.pdf",
                                        created_at=course.created_at + timedelta(days=j + 1))
            pdf = make_pdf(title, [f"Course: {course.title}", "Demo material generated by seed_demo_data.",
                                   f"Topic {j + 1} of {len(topics)}."])
            material.file.save(f"{slugify(topic)}.pdf", ContentFile(pdf), save=False)
            material.save()

    def _seed_assignments(self, idx, course):
        for title, instructions, max_marks, offset in plan.assignment_plan(idx):
            if Assignment.objects.filter(course=course, title=title).exists():
                continue
            deadline = self.now + timedelta(days=offset)
            assignment = Assignment.objects.create(
                course=course, title=title, instructions=instructions, deadline=deadline, max_marks=max_marks,
                created_at=min(self.now - timedelta(days=1), deadline - timedelta(days=14)))
            if offset > 0 and course.is_published:
                self.new_future_assignments.append(assignment)

    # ------------------------------------------------------------------ enrolment and requests
    def _seed_public_enrollments(self):
        for si, student in enumerate(self.students):
            for ci in plan.PUBLIC_COURSE_INDEXES:
                if not plan.public_enrollment(si, ci):
                    continue
                course = self.courses[ci]
                try:
                    created = enroll_student(student, course)
                except BusinessRuleError:
                    continue
                if created:
                    when = self.now - timedelta(days=20 + (si * 3 + ci) % 25)
                    Enrollment.objects.filter(student=student, course=course).update(enrolled_at=when)
                    self._backdate(Notification.objects.filter(
                        recipient=course.teacher, dedupe_key=f"enrolled:{course.pk}:{student.pk}"), when)

    def _seed_private_requests(self):
        for position, ci in enumerate(plan.PRIVATE_COURSE_INDEXES):
            course = self.courses[ci]
            teacher = course.teacher
            for si, student in enumerate(self.students):
                state = plan.private_state(si, position)
                if state is None or CourseAccessRequest.objects.filter(course=course, student=student).exists():
                    continue
                try:
                    access = private.request_access(student, course)
                    requested = self.now - timedelta(days=15 + (si + position) % 25)
                    decided = requested + timedelta(days=1)
                    if state == "approved":
                        private.approve_request(teacher, access.pk)
                    elif state == "rejected":
                        private.reject_request(teacher, access.pk)
                    elif state == "revoked":
                        private.approve_request(teacher, access.pk)
                        private.revoke_student(teacher, course, student)
                except BusinessRuleError as exc:
                    self.stderr.write(self.style.WARNING(f"{student.email} / {course.title}: {exc}"))
                    continue
                CourseAccessRequest.objects.filter(pk=access.pk).update(
                    requested_at=requested, decided_at=None if state == "pending" else decided)
                if state in ("approved",):
                    Enrollment.objects.filter(student=student, course=course).update(enrolled_at=decided)
                self._backdate(Notification.objects.filter(dedupe_key__startswith=f"access:{access.pk}:"), decided)
                self._backdate(Notification.objects.filter(dedupe_key=f"access-request:{access.pk}"), requested)

    # ------------------------------------------------------------------ progress, submissions, marks
    def _seed_activity(self):
        index_of = {s.pk: i for i, s in enumerate(self.students)}
        for ci, course in self.courses.items():
            materials = list(course.materials.order_by("created_at", "id"))
            assignments = list(course.assignments.order_by("deadline", "id"))
            for enrollment in Enrollment.objects.filter(course=course).select_related("student"):
                si = index_of.get(enrollment.student_id)
                if si is None:
                    continue
                self._seed_one_enrollment(enrollment, si, ci, materials, assignments)
            sync_course_progress(course)

    def _seed_one_enrollment(self, enrollment, si, ci, materials, assignments):
        student, level = enrollment.student, plan.progress_profile(si, ci)
        if level == 0:
            return
        viewed = materials[:1] if level == 1 else materials
        for k, material in enumerate(viewed):
            MaterialAccess.objects.get_or_create(
                student=student, material=material,
                defaults={"first_accessed_at": enrollment.enrolled_at + timedelta(hours=3 + k)})
        if enrollment.last_accessed_at is None:
            Enrollment.objects.filter(pk=enrollment.pk).update(
                last_accessed_at=self.now - timedelta(hours=(si * 7 + ci * 5) % 200 + 1))
        if level < 3 or len(assignments) < 2:
            return
        first, second = assignments[0], assignments[1]
        if level == 5:
            submission = self._submit(student, first, first.deadline + timedelta(hours=20))
            if submission and si % 2 == 0:
                self._review(submission, si, 0, ci)
            return
        submission = self._submit(student, first, first.deadline - timedelta(days=1))
        if level == 4:
            if submission:
                self._review(submission, si, 0, ci)
            when = second.deadline - timedelta(hours=5) if second.deadline < self.now else self.now - timedelta(hours=6)
            self._submit(student, second, when)

    def _submit(self, student, assignment, when):
        if Submission.objects.filter(assignment=assignment, student=student).exists():
            return None
        label = f"{slugify(student.name)}-{slugify(assignment.title)}"[:100]
        submission = Submission(assignment=assignment, student=student, original_name=f"{label}.pdf",
                                submitted_at=when, is_late=when > assignment.deadline)
        pdf = make_pdf(f"{student.name} - {assignment.title}", ["Demo submission generated by seed_demo_data."])
        submission.file.save(f"{label}.pdf", ContentFile(pdf), save=False)
        submission.save()
        note = notify(assignment.course.teacher, Cat.ASSIGNMENTS,
                      f"{student.name} submitted '{assignment.title}' in {assignment.course.title}.",
                      reverse("assignments:teacher_detail", args=[assignment.pk]), f"submission:{submission.pk}")
        if note:
            self._backdate(Notification.objects.filter(pk=note.pk), when)
        return submission

    def _review(self, submission, si, ai, ci):
        if submission.reviewed:
            return
        maximum = submission.assignment.max_marks
        ratio = 0.55 + ((si * 13 + ai * 7 + ci) % 45) / 100
        marks = Decimal(str(round(maximum * ratio * 2) / 2))
        save_review(submission, marks, plan.FEEDBACK[(si + ci) % len(plan.FEEDBACK)])
        reviewed_at = min(self.now, submission.submitted_at + timedelta(days=2))
        Submission.objects.filter(pk=submission.pk).update(reviewed_at=reviewed_at)
        self._backdate(Notification.objects.filter(dedupe_key=f"review:{submission.pk}"), reviewed_at)

    # ------------------------------------------------------------------ announcements and discussion
    def _seed_announcements_and_discussion(self):
        for ci, course in self.courses.items():
            if not course.is_published:
                continue
            for title, body, offset in plan.announcement_plan(ci):
                if Announcement.objects.filter(course=course, title=title).exists():
                    continue
                when = self.now + timedelta(days=offset)
                announcement = Announcement.objects.create(
                    course=course, author=course.teacher, title=title, body=body, created_at=when)
                notify_announcement(announcement)
                self._backdate(Notification.objects.filter(dedupe_key=f"announcement:{announcement.pk}"), when)
            self._seed_discussion(ci, course)

    def _post(self, course, author, body, parent, when):
        existing = Post.objects.filter(course=course, author=author, body=body, parent=parent).first()
        if existing:
            return existing
        post = Post.objects.create(course=course, author=author, body=body, parent=parent, created_at=when)
        notify_post(post)
        self._backdate(Notification.objects.filter(dedupe_key__startswith=f"post:{post.pk}:"), when)
        return post

    def _seed_discussion(self, ci, course):
        members = [e.student for e in Enrollment.objects.filter(
            course=course, student__email__iendswith="@" + plan.DEMO_DOMAIN).select_related("student").order_by("id")]
        if len(members) < 3:
            return
        topics = plan.COURSES[ci][6]
        base = self.now - timedelta(days=8 + ci % 5)
        q1 = self._post(course, members[0], plan.QUESTIONS[ci % 3].format(topic=topics[ci % 3]), None, base)
        self._post(course, course.teacher, plan.TEACHER_REPLIES[ci % 2], q1, base + timedelta(hours=5))
        self._post(course, members[1], plan.STUDENT_REPLIES[ci % 2], q1, base + timedelta(hours=9))
        # an unanswered question, so the empty/pending state and moderation can be tried
        self._post(course, members[2], plan.QUESTIONS[(ci + 1) % 3].format(topic=topics[(ci + 1) % 3]), None,
                   self.now - timedelta(hours=20 + ci))

    # ------------------------------------------------------------------ favourites and notifications
    def _seed_favourites(self):
        for si, student in enumerate(self.students):
            for ci, course in self.courses.items():
                if plan.favourite(si, ci):
                    Favourite.objects.get_or_create(
                        student=student, course=course,
                        defaults={"created_at": self.now - timedelta(days=(si + ci) % 20 + 1)})

    def _seed_notifications(self):
        """A few welcome notes for the main test accounts, then a read/unread mix (first run only)."""
        student1 = self.students[0]
        first_run = notify(student1, Cat.COURSES,
                           "Welcome to the LearnHub demo. Browse the catalogue and enrol in a public course.",
                           reverse("courses:browse"), "demo:welcome") is not None
        notify(student1, Cat.DISCUSSION, "Tip: open a course's Discussion page to ask a question.",
               reverse("courses:browse"), "demo:tip")
        if not first_run:
            return  # keep whatever the person has already read or left unread
        demo_notes = Notification.objects.filter(recipient__email__iendswith="@" + plan.DEMO_DOMAIN)
        # mark roughly every other older notification as read so both states exist
        for note in demo_notes.filter(created_at__lt=self.now - timedelta(days=4)):
            if note.pk % 2 == 0:
                Notification.objects.filter(pk=note.pk).update(read_at=note.created_at + timedelta(hours=2))

    # ------------------------------------------------------------------ credentials note
    def _write_credentials(self):
        rows = User.objects.filter(email__iendswith="@" + plan.DEMO_DOMAIN).order_by("role", "email")
        lines = [
            "# LearnHub demo logins (LOCAL ONLY)",
            "",
            "**Do not commit, share or deploy this file.** It is listed in `.gitignore` and is excluded from release ZIPs.",
            "These accounts exist only for testing. Their e-mail addresses end in `.test`, which can never receive mail.",
            "",
            f"Password: `{self.password}`",
            "",
            "The same password is used for every demo account. Sign in with the e-mail address as the username.",
            "",
            "| E-mail | Role | Status | Student / Teacher ID |",
            "|---|---|---|---|",
        ]
        for u in rows:
            lines.append(f"| {u.email} | {u.get_role_display()} | {u.get_status_display()} | {u.public_id or '-'} |")
        lines += [
            "",
            "Suggested starting points: `student01` (every request state, most courses), `teacher01` (two courses, pending requests),",
            f"`{plan.ADMIN_EMAIL}` (administrator), `pending.teacher01` (waiting for approval).",
            "",
        ]
        self.credentials_path.write_text("\n".join(lines), encoding="utf-8")
        try:
            self.credentials_path.chmod(0o600)
        except OSError:
            pass

    # ------------------------------------------------------------------ verification
    def verify(self):
        """Return [(label, ok, detail)] computed from the database. Read-only."""
        results = []

        def check(label, ok, detail=""):
            results.append((label, bool(ok), detail))

        demo = User.objects.filter(email__iendswith="@" + plan.DEMO_DOMAIN)
        teachers = demo.filter(role="teacher", status="active")
        students = demo.filter(role="student", status="active")
        n_t = teachers.filter(email_verified=True, public_id__startswith="TCH-").count()
        n_s = students.filter(email_verified=True, public_id__startswith="STU-").count()
        check("Approved, verified teachers with a TCH- ID (>= 15)", n_t >= plan.TEACHER_COUNT, n_t)
        check("Active, verified students with a STU- ID (>= 50)", n_s >= 50, n_s)
        check("Every demo account is e-mail verified", not demo.filter(email_verified=False).exists(),
              f"{demo.count()} accounts")
        ids = list(demo.exclude(public_id__isnull=True).values_list("public_id", flat=True))
        check("Student/Teacher IDs are unique", len(ids) == len(set(ids)), f"{len(ids)} IDs")
        check("Pending demo teachers wait for approval, verified, no ID yet",
              demo.filter(role="teacher", status="pending", email_verified=True, public_id__isnull=True).count()
              == len(plan.PENDING_TEACHERS))

        courses = Course.objects.filter(teacher__in=teachers)
        public_n = courses.filter(access="public").count()
        private_n = courses.filter(access="private").count()
        check("Courses (>= 15)", courses.count() >= 15, courses.count())
        check("Public courses (>= 10)", public_n >= 10, public_n)
        check("Private courses (>= 5)", private_n >= 5, private_n)
        owners = courses.order_by().values("teacher").distinct().count()  # order_by(): ignore Meta ordering
        check("Courses belong to several teachers (>= 10)", owners >= 10, owners)
        check("Every private course has an invitation token",
              not courses.filter(access="private", invite_token__isnull=True).exists())
        check("Every demo course has materials and assignments",
              not courses.filter(materials__isnull=True).exists() and not courses.filter(assignments__isnull=True).exists())

        enrollments = Enrollment.objects.filter(course__in=courses, student__in=demo)
        stale = sum(1 for e in enrollments.select_related("student", "course")
                    if e.progress != compute_progress(e.student, e.course))
        check("Enrollments exist", enrollments.exists(), enrollments.count())
        check("Stored progress equals the recomputed value", stale == 0, f"{stale} mismatches")
        check("Several progress levels exist",
              enrollments.filter(progress=0).exists() and enrollments.filter(progress=100).exists()
              and enrollments.filter(progress__gt=0, progress__lt=100).exists())
        check("Recently-viewed timestamps exist", enrollments.filter(last_accessed_at__isnull=False).exists())

        requests = CourseAccessRequest.objects.filter(course__in=courses.filter(access="private"))
        by_status = {s: requests.filter(status=s).count() for s in ("pending", "approved", "rejected", "revoked")}
        check("Access requests in all four states", all(by_status.values()), by_status)
        private_enrol = Enrollment.objects.filter(course__in=courses.filter(access="private"))
        enrolled_pairs = set(private_enrol.values_list("course_id", "student_id"))
        approved_pairs = set(requests.filter(status="approved").values_list("course_id", "student_id"))
        check("Private enrolment exists exactly for approved requests", enrolled_pairs == approved_pairs,
              f"{len(enrolled_pairs)} enrolments / {len(approved_pairs)} approved")

        subs = Submission.objects.filter(assignment__course__in=courses)
        check("Submissions exist (on time, late, reviewed, unreviewed)",
              subs.filter(is_late=False).exists() and subs.filter(is_late=True).exists()
              and subs.filter(reviewed=True).exists() and subs.filter(reviewed=False).exists(), subs.count())
        check("Reviewed submissions have marks within the maximum",
              not subs.filter(reviewed=True, marks__isnull=True).exists()
              and not subs.filter(marks__gt=F("assignment__max_marks")).exists())
        wrong_late = sum(1 for s in subs.select_related("assignment") if s.is_late != (s.submitted_at > s.assignment.deadline))
        check("Late flag matches submission time and deadline", wrong_late == 0, f"{wrong_late} mismatches")

        check("Announcements exist", Announcement.objects.filter(course__in=courses).exists())
        questions = Post.objects.filter(course__in=courses, parent__isnull=True)
        check("Discussion questions and replies exist",
              questions.exists() and Post.objects.filter(course__in=courses, parent__isnull=False).exists())
        check("An unanswered question exists", questions.filter(replies__isnull=True).exists())
        check("Favourites exist", Favourite.objects.filter(student__in=demo).exists())
        notes = Notification.objects.filter(recipient__in=demo)
        check("Notifications exist, read and unread", notes.filter(read_at__isnull=True).exists()
              and notes.filter(read_at__isnull=False).exists(), notes.count())
        return results

    def _report(self, results):
        self.stdout.write("")
        self.stdout.write("Verification (computed from the database just now):")
        failed = 0
        for label, ok, detail in results:
            mark = self.style.SUCCESS("PASS") if ok else self.style.ERROR("FAIL")
            self.stdout.write(f"  [{mark}] {label}" + (f"  ({detail})" if detail != "" else ""))
            failed += 0 if ok else 1
        if failed:
            raise CommandError(f"{failed} verification check(s) failed.")
        self.stdout.write(self.style.SUCCESS("All checks passed."))
