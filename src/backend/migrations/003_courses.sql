-- C02: courses and course members (specs/identity-access.md §3, ADR-013).
-- D-10: numbered as main's max (002) + 1; renumber to the new max + 1 before merge if main
-- already has 003. Rollback: restore backups/*-before-003.sqlite (src/backend/README.md).
--
-- Course columns follow Course/CourseCreate in src/contracts/api.v1.yaml; the publish
-- pointer columns follow specs/teacher-review-publish.md「courses 增加」 and are only
-- maintained by the G tasks (published_version_id gains no FK here: its table is G02's).
CREATE TABLE courses (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) BETWEEN 32 AND 64),
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    description TEXT CHECK (description IS NULL OR length(description) <= 1000),
    -- creator, display only; never used for authorization (§3.2.3)
    teacher_id TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    published_version_id TEXT,
    published_version INTEGER CHECK (published_version IS NULL OR published_version >= 1),
    draft_revision INTEGER NOT NULL DEFAULT 0 CHECK (draft_revision >= 0),
    published_from_revision INTEGER,
    -- pointer and user-facing number are maintained in the same transaction
    CHECK ((published_version_id IS NULL) = (published_version IS NULL))
);

-- In-course role is independent of the account type users.role; one role per (course, user).
-- No ON DELETE action: courses and users are never deleted while memberships reference them.
CREATE TABLE course_members (
    course_id TEXT NOT NULL REFERENCES courses(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('teacher', 'student')),
    -- NULL when added from the command line (§3.1)
    added_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (course_id, user_id)
);

CREATE INDEX idx_course_members_user_id ON course_members(user_id);

-- IAM-24: a student account can never hold a teacher member row, whatever writes it.
-- An unknown user_id falls through to the foreign key error instead.
CREATE TRIGGER course_members_teacher_needs_teacher_account_insert
BEFORE INSERT ON course_members
WHEN NEW.role = 'teacher'
    AND EXISTS (SELECT 1 FROM users WHERE id = NEW.user_id AND role <> 'teacher')
BEGIN
    SELECT RAISE(ABORT, 'course_members: teacher member requires a teacher account');
END;

CREATE TRIGGER course_members_teacher_needs_teacher_account_update
BEFORE UPDATE OF role, user_id ON course_members
WHEN NEW.role = 'teacher'
    AND EXISTS (SELECT 1 FROM users WHERE id = NEW.user_id AND role <> 'teacher')
BEGIN
    SELECT RAISE(ABORT, 'course_members: teacher member requires a teacher account');
END;
