from __future__ import annotations

from pathlib import Path

from mastery_ledger.models import FolderPickerResult


def pick_folder(initial_path: str | None = None) -> FolderPickerResult:
    """Open an OS folder chooser after an explicit learner action."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return FolderPickerResult(
            status="unavailable",
            message="This Python runtime does not include the native folder-picker module.",
        )

    initial = None
    if initial_path:
        candidate = Path(initial_path).expanduser()
        if candidate.is_dir():
            initial = str(candidate.resolve(strict=False))
        elif candidate.parent.is_dir():
            initial = str(candidate.parent.resolve(strict=False))

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        selected = filedialog.askdirectory(
            parent=root,
            initialdir=initial,
            title="Choose a Mastery Ledger learning workspace",
            mustexist=False,
        )
    except (tk.TclError, OSError) as error:
        return FolderPickerResult(
            status="unavailable",
            message=f"The native folder chooser is unavailable: {error}",
        )
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass

    if not selected:
        return FolderPickerResult(status="cancelled", message="No folder was selected.")
    return FolderPickerResult(status="selected", path=str(Path(selected).resolve(strict=False)))
