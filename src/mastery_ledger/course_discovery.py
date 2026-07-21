from __future__ import annotations

from pathlib import Path


MAX_COURSES = 500
COURSE_MANIFESTS = ("course.yaml", "study.yaml")


def _is_course(path: Path) -> bool:
    return any((path / manifest).is_file() for manifest in COURSE_MANIFESTS)


def course_roots(workspace: Path) -> list[Path]:
    """Return course folders for either a single-course or collection workspace."""
    if not workspace.is_dir() or workspace.is_symlink():
        return []

    # A selected course folder is a complete workspace. Treating it as terminal
    # also prevents internal folders from being mistaken for nested courses.
    if _is_course(workspace):
        return [workspace]

    parents: list[Path] = []
    courses_dir = workspace / "courses"
    if courses_dir.is_dir() and not courses_dir.is_symlink():
        parents.append(courses_dir)
    parents.append(workspace)

    roots: list[Path] = []
    seen: set[Path] = set()
    for parent in parents:
        try:
            children = sorted(parent.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            continue
        for child in children:
            if len(roots) >= MAX_COURSES:
                return roots
            if not child.is_dir() or child.is_symlink() or not _is_course(child):
                continue
            resolved = child.resolve(strict=False)
            if resolved in seen:
                continue
            roots.append(child)
            seen.add(resolved)
    return roots
