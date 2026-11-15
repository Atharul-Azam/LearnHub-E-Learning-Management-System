"""Static data and deterministic planning rules for ``manage.py seed_demo_data``.

Pure Python (no Django imports) so the plan can be inspected and unit-tested
without a database. Everything here is fictional. Demo e-mail addresses use the
reserved ``.test`` top-level domain, so they can never reach a real mailbox.
"""
DEMO_DOMAIN = "demo.learnhub.test"
ADMIN_EMAIL = f"admin@{DEMO_DOMAIN}"
TEACHER_COUNT = 15  # approved teachers
PENDING_TEACHER_COUNT = 2  # waiting for the administrator (to test UC3 / approval)
STUDENT_COUNT = 55


def teacher_email(n):  # n is 1-based
    return f"teacher{n:02d}@{DEMO_DOMAIN}"


def pending_teacher_email(n):
    return f"pending.teacher{n:02d}@{DEMO_DOMAIN}"


def student_email(n):
    return f"student{n:02d}@{DEMO_DOMAIN}"


# --------------------------------------------------------------------------- people
TEACHERS = [
    ("Dr. Farhana Rahman", "Python, software engineering", "Lecturer in computer science with ten years of teaching experience."),
    ("Prof. Imran Hossain", "Web development, JavaScript", "Builds and teaches modern web applications."),
    ("Dr. Nusrat Jahan", "Data analysis, statistics", "Works with data teams and loves clear charts."),
    ("Dr. Tanvir Ahmed", "Machine learning", "Researcher focused on practical machine learning."),
    ("Mr. Sabbir Khan", "Databases, SQL", "Database engineer turned instructor."),
    ("Dr. Maliha Chowdhury", "Calculus, analysis", "Mathematics lecturer who explains ideas visually."),
    ("Prof. Arif Mahmud", "Linear algebra", "Teaches applied mathematics for engineers."),
    ("Ms. Sadia Islam", "Digital marketing", "Marketing consultant for small businesses."),
    ("Ms. Rumana Akter", "UI/UX design", "Product designer and design mentor."),
    ("Dr. Kamal Uddin", "Academic writing, English", "Language teacher and thesis supervisor."),
    ("Dr. Shirin Sultana", "Physics", "Physics educator with a lab background."),
    ("Mr. Rafiq Karim", "Communication", "Corporate trainer in presentation skills."),
    ("Mr. Zahid Hasan", "Algorithms, competitive programming", "Former contest coach."),
    ("Ms. Taslima Begum", "Entrepreneurship", "Startup mentor and founder."),
    ("Mr. Nayeem Sarker", "Educational technology", "New to LearnHub; has not created a course yet."),
]
PENDING_TEACHERS = [
    ("Ms. Lubna Yasmin", "Chemistry", "Applied for a teacher account."),
    ("Mr. Hasan Mahbub", "Economics", "Applied for a teacher account."),
]

FIRST_NAMES = [
    "Ayesha", "Rahim", "Nabila", "Karim", "Tasnim", "Sakib", "Mim", "Fahim", "Sumaiya", "Rafi",
    "Jannat", "Tahmid", "Anika", "Shihab", "Ritu", "Mahir", "Lamia", "Nafis", "Farzana", "Asif",
    "Sharmin", "Omar", "Priya", "Ishrat", "Rakib", "Samira", "Zubair", "Tania", "Arman", "Mehnaz",
]
LAST_NAMES = [
    "Ahmed", "Hossain", "Rahman", "Khan", "Islam", "Chowdhury", "Akter", "Sarker", "Mia", "Uddin",
    "Siddique", "Karim", "Begum", "Roy", "Das", "Haque", "Sultana", "Mondal", "Talukder", "Bhuiyan",
]


def student_name(i):  # i is 0-based
    return f"{FIRST_NAMES[i % 30]} {LAST_NAMES[(3 * i + i // 30) % 20]}"


def student_theme(i):
    """A few students use the dark theme / serif font so Settings can be checked."""
    return "dark" if i % 7 == 3 else "system"


def student_font(i):
    return "serif" if i % 11 == 5 else "sans"


# --------------------------------------------------------------------------- courses
CATEGORY_COLOURS = {
    "Programming": (79, 70, 229),
    "Web Development": (14, 116, 144),
    "Data Science": (5, 150, 105),
    "Databases": (180, 83, 9),
    "Mathematics": (190, 24, 93),
    "Business": (71, 85, 105),
    "Design": (147, 51, 234),
    "Languages": (3, 105, 161),
    "Science": (21, 128, 61),
}

# key: (title, category, teacher number (1-based), access, visibility, description, three topics)
COURSES = [
    ("Python Programming Fundamentals", "Programming", 1, "public", "published",
     "Start programming from zero: variables, control flow, functions, files and small projects.",
     ["Variables and data types", "Functions and modules", "Working with files"]),
    ("Web Development with HTML, CSS and JavaScript", "Web Development", 2, "public", "published",
     "Build responsive pages and add interactivity with vanilla JavaScript.",
     ["Semantic HTML", "Responsive layout with CSS", "DOM and events"]),
    ("Data Analysis with Pandas and NumPy", "Data Science", 3, "public", "published",
     "Clean, explore and visualise real datasets using the Python data stack.",
     ["NumPy arrays", "DataFrames and cleaning", "Visualising results"]),
    ("Introduction to Machine Learning", "Data Science", 4, "public", "published",
     "Core ideas of supervised learning with hands-on examples in scikit-learn.",
     ["Regression", "Classification", "Model evaluation"]),
    ("Database Systems and SQL", "Databases", 5, "public", "published",
     "Relational modelling, normalisation and writing confident SQL queries.",
     ["ER modelling", "SELECT and joins", "Transactions"]),
    ("Calculus I", "Mathematics", 6, "public", "published",
     "Limits, derivatives and their applications, taught with plenty of worked examples.",
     ["Limits", "Derivatives", "Applications of derivatives"]),
    ("Linear Algebra Essentials", "Mathematics", 7, "public", "published",
     "Vectors, matrices and linear transformations for engineering and data work.",
     ["Vectors and matrices", "Systems of equations", "Eigenvalues"]),
    ("Digital Marketing Basics", "Business", 8, "public", "published",
     "Plan campaigns, understand audiences and measure results across digital channels.",
     ["Audience research", "Content and social media", "Measuring campaigns"]),
    ("UI/UX Design Principles", "Design", 9, "public", "published",
     "Design usable interfaces: research, wireframes, visual hierarchy and testing.",
     ["User research", "Wireframing", "Usability testing"]),
    ("Academic English Writing", "Languages", 10, "public", "published",
     "Structure arguments, cite sources and write clearly for university study.",
     ["Essay structure", "Citing sources", "Editing and proofreading"]),
    ("Introduction to Physics", "Science", 11, "public", "published",
     "Mechanics, energy and waves with everyday examples.",
     ["Motion and forces", "Work and energy", "Waves"]),
    ("Public Speaking (draft)", "Business", 12, "public", "hidden",
     "A hidden draft course: visible only to its teacher, useful to test the Hide/Publish action.",
     ["Overcoming nerves", "Structuring a talk", "Delivery"]),
    ("Advanced Algorithms Study Group", "Programming", 1, "private", "published",
     "Invitation-only study group on graph algorithms and dynamic programming.",
     ["Graph traversal", "Shortest paths", "Dynamic programming"]),
    ("Capstone Project Workshop", "Programming", 2, "private", "published",
     "Private workshop for final-year project teams: planning, reviews and demos.",
     ["Project planning", "Code reviews", "Demo preparation"]),
    ("Thesis Writing Clinic", "Languages", 10, "private", "published",
     "Small-group clinic for students currently writing a thesis.",
     ["Literature review", "Methodology chapter", "Responding to feedback"]),
    ("Competitive Programming Bootcamp", "Programming", 13, "private", "published",
     "Invitation-only contest practice with weekly problem sets.",
     ["Complexity analysis", "Greedy strategies", "Contest practice"]),
    ("Entrepreneurship Mentoring Cohort", "Business", 14, "private", "published",
     "Mentored cohort for student founders: validation, pricing and pitching.",
     ["Customer validation", "Pricing", "Pitching"]),
]

PUBLIC_COURSE_INDEXES = [i for i, c in enumerate(COURSES) if c[3] == "public"]
PRIVATE_COURSE_INDEXES = [i for i, c in enumerate(COURSES) if c[3] == "private"]
INVITE_EXPIRY = {12: "never", 13: "30", 14: "7", 15: "never", 16: "90"}  # course index -> choice


# --------------------------------------------------------------------------- planning rules
def public_enrollment(student_i, course_i):
    """Is student ``student_i`` (0-based) enrolled in public published course ``course_i``?"""
    if COURSES[course_i][3] != "public" or COURSES[course_i][4] != "published":
        return False
    if student_i < 3:  # the first three students are enrolled everywhere: easy to test with
        return True
    return (student_i * 5 + course_i * 7) % 11 < 4


def private_state(student_i, private_pos):
    """Final state of the student's request for the ``private_pos``-th private course.

    Returns None (no request), "pending", "approved", "rejected" or "revoked".
    """
    if student_i == 0:  # student01 sees every state; the last course has no request so
        return ["approved", "pending", "rejected", "revoked", None][private_pos]  # the join link can be tried
    if student_i in (1, 2):
        return "approved" if private_pos in (0, 2) else None
    r = (student_i * 3 + private_pos * 2) % 10
    if r in (0, 1):
        return "approved"
    if r == 2:
        return "pending"
    if r == 3:
        return "rejected"
    if r == 4 and student_i % 2 == 0:
        return "revoked"
    return None


def progress_profile(student_i, course_i):
    """0 = not started ... 5 = everything done (see the seeder for what each means)."""
    if student_i == 0:
        return (course_i % 5) + 1 if course_i % 6 else 0
    return (student_i + course_i * 3) % 6


def favourite(student_i, course_i):
    if COURSES[course_i][3] != "public" or COURSES[course_i][4] != "published":
        return False
    if student_i == 0:
        return course_i in (0, 2, 4)
    return (student_i + course_i) % 6 == 0


def assignment_plan(course_i):
    """Two assignments per course: (title, instructions, max_marks, deadline offset in days)."""
    title, _cat, _t, _a, _v, _d, topics = COURSES[course_i]
    second_offsets = [-3, 1, 6, 14]
    return [
        (f"Assignment 1: {topics[0]}", f"Complete the exercises on '{topics[0]}' and submit one PDF.", 20, -12),
        (f"Assignment 2: {topics[1]}", f"Apply '{topics[1]}' to the case study shared in class and submit one PDF.", 30,
         second_offsets[course_i % 4]),
    ]


FEEDBACK = [
    "Good work. Clear structure and correct reasoning.",
    "Solid attempt. Please show your steps more explicitly next time.",
    "Excellent. Well organised and easy to follow.",
    "Some parts are missing; see the marked sections and revise your approach.",
    "Nice effort, and the conclusion is convincing. Check the units in question 3.",
]

QUESTIONS = [
    "Could you explain '{topic}' once more with a different example?",
    "I am stuck on the exercise for '{topic}'. Where should I start?",
    "Is '{topic}' going to be part of the final assessment?",
]
STUDENT_REPLIES = [
    "I had the same problem. Re-reading the lecture notes helped me.",
    "Try breaking the exercise into smaller steps and checking each one.",
]
TEACHER_REPLIES = [
    "Good question. I will post a worked example in the materials this week.",
    "Yes, it is covered in the assessment. Focus on the main idea first.",
]


def announcement_plan(course_i):
    title = COURSES[course_i][0]
    return [
        (f"Welcome to {title}", "Welcome! Please read the first material and introduce yourself in the discussion.", -20),
        ("Assignment 1 reminder", "Assignment 1 is due soon. Submit a single PDF through the course page.", -9),
    ]


if __name__ == "__main__":  # quick self-check:  python core/demo_data.py
    names = {student_name(i) for i in range(STUDENT_COUNT)}
    assert len(names) == STUDENT_COUNT
    assert len(TEACHERS) == TEACHER_COUNT
    assert sum(1 for c in COURSES if c[3] == "public") >= 10 and sum(1 for c in COURSES if c[3] == "private") >= 5
    print("demo_data ok")
