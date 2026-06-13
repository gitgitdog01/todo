#!/usr/bin/env python3
"""CLI todo manager — stdlib only."""

import base64
import json
import os
import shutil
import sys
import argparse
import tempfile
from datetime import datetime
from pathlib import Path

DATA_DIR        = Path.home() / ".local" / "share" / "todo"
DATA_FILE       = DATA_DIR / "todos.json"
ATTACHMENTS_DIR = DATA_DIR / "attachments"

PRIORITY_ALIASES = {
    "high": "HIGH",   "h": "HIGH",
    "medium": "MEDIUM", "med": "MEDIUM", "m": "MEDIUM",
    "low": "LOW",     "l": "LOW",
}
PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# ── ANSI ──────────────────────────────────────────────────────────────────────

_color = "NO_COLOR" not in os.environ and sys.stdout.isatty()
_image = "NO_IMAGE" not in os.environ and sys.stdout.isatty()

def _e(code: str) -> str:
    return code if _color else ""

RST    = _e("\033[0m")
BOLD   = _e("\033[1m")
DIM    = _e("\033[2m")
STRIKE = _e("\033[9m")
RED    = _e("\033[31m")
YELLOW = _e("\033[33m")
GREEN  = _e("\033[32m")
CYAN   = _e("\033[36m")

PRIORITY_STYLE = {"HIGH": RED + BOLD, "MEDIUM": YELLOW, "LOW": DIM}

# ── I/O ───────────────────────────────────────────────────────────────────────

def load() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        return {"next_id": 1, "todos": []}
    with DATA_FILE.open(encoding="utf-8") as f:
        return json.load(f)

def save(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=".todos_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, DATA_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

def find_todo(todos: list, tid: int):
    return next((t for t in todos if t["id"] == tid), None)

def die(msg: str) -> None:
    print(f"{RED}Error:{RST} {msg}", file=sys.stderr)
    sys.exit(1)

# ── Attachments ───────────────────────────────────────────────────────────────

def attach_image(todo_id: int, image_path: str) -> dict:
    src = Path(image_path).expanduser().resolve()
    if not src.exists():
        die(f"image not found: {image_path}")
    if not src.is_file():
        die(f"not a file: {image_path}")
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix or ".png"
    dst = ATTACHMENTS_DIR / f"{todo_id}_{src.name}"
    counter = 1
    while dst.exists():
        dst = ATTACHMENTS_DIR / f"{todo_id}_{counter}{suffix}"
        counter += 1
    shutil.copy2(src, dst)
    return {
        "path": str(dst),
        "added_at": datetime.now().isoformat(timespec="seconds"),
    }

def delete_attachments(todo: dict) -> None:
    for img in todo.get("images", []):
        try:
            p = Path(img["path"])
            if p.exists():
                p.unlink()
        except OSError:
            pass

# ── Terminal image display ────────────────────────────────────────────────────

def _is_kitty() -> bool:
    return os.environ.get("TERM") == "xterm-kitty" or "KITTY_WINDOW_ID" in os.environ

def _is_iterm2() -> bool:
    return "ITERM_SESSION_ID" in os.environ

def _is_png(path: Path) -> bool:
    try:
        return path.read_bytes()[:4] == b"\x89PNG"
    except OSError:
        return False

def _show_image_kitty(path: Path) -> None:
    # Kitty Graphics Protocol only supports PNG directly (f=100)
    if not _is_png(path):
        print(f"  [image] {path}")
        return
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    chunk_size = 4096
    first = True
    while data:
        chunk = data[:chunk_size]
        data = data[chunk_size:]
        more = "1" if data else "0"
        if first:
            sys.stdout.write(f"\033_Ga=T,f=100,m={more};" + chunk + "\033\\")
            first = False
        else:
            sys.stdout.write(f"\033_Gm={more};" + chunk + "\033\\")
        sys.stdout.flush()
    print()

def _show_image_iterm2(path: Path) -> None:
    raw = path.read_bytes()
    data = base64.standard_b64encode(raw).decode("ascii")
    name = base64.standard_b64encode(path.name.encode()).decode("ascii")
    header = f"name={name};size={len(raw)};inline=1"
    sys.stdout.write(f"\033]1337;File={header}:{data}\a\n")
    sys.stdout.flush()

def show_image(path_str: str) -> None:
    if not _image:
        print(f"  [image] {path_str}")
        return
    p = Path(path_str)
    if not p.exists():
        print(f"  {DIM}[image not found: {path_str}]{RST}")
        return
    if _is_kitty():
        _show_image_kitty(p)
    elif _is_iterm2():
        _show_image_iterm2(p)
    else:
        print(f"  [image] {path_str}")

# ── Display ───────────────────────────────────────────────────────────────────

def _marker(priority: str) -> str:
    raw = {"HIGH": "!!!", "MEDIUM": "!", "LOW": "·"}[priority]
    return PRIORITY_STYLE[priority] + raw.center(3) + RST

def format_todo(todo: dict) -> str:
    num    = f"{DIM}{todo['id']:>3}{RST}"
    marker = _marker(todo["priority"])
    if todo["done"]:
        text  = f"{DIM}{STRIKE}{todo['text']}{RST}"
        check = f"{GREEN}✓{RST} "
    else:
        text  = todo["text"]
        check = "  "
    attachment = (" 📎" if _color else " [+img]") if todo.get("images") else ""
    return f"  {num}  {marker}  {check}{text}{attachment}"

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_add(args) -> None:
    text     = " ".join(args.text)
    p_input  = (args.priority or "medium").lower()
    priority = PRIORITY_ALIASES.get(p_input)
    if priority is None:
        die(f"unknown priority '{args.priority}' — use high / medium / low")

    data = load()
    todo = {
        "id":         data["next_id"],
        "text":       text,
        "priority":   priority,
        "done":       False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "images":     [],
    }
    if args.image:
        todo["images"].append(attach_image(data["next_id"], args.image))
    data["todos"].append(todo)
    data["next_id"] += 1
    save(data)
    print(f"{GREEN}Added{RST}   {format_todo(todo)}")


def cmd_list(args) -> None:
    data  = load()
    todos = data["todos"]

    if getattr(args, "priority", None):
        p = PRIORITY_ALIASES.get(args.priority.lower())
        if p is None:
            die(f"unknown priority '{args.priority}'")
        todos = [t for t in todos if t["priority"] == p]

    if not getattr(args, "all", False):
        todos = [t for t in todos if not t["done"]]

    todos = sorted(todos, key=lambda t: (t["done"], PRIORITY_ORDER[t["priority"]], t["id"]))

    if not todos:
        print(f"{DIM}No todos.{RST}")
        return

    for todo in todos:
        print(format_todo(todo))


def cmd_done(args) -> None:
    data = load()
    changed, already, missing = [], [], []

    for tid in args.id:
        todo = find_todo(data["todos"], tid)
        if todo is None:
            missing.append(tid)
        elif todo["done"]:
            already.append(tid)
        else:
            todo["done"] = True
            changed.append(todo)

    if changed:
        save(data)
        for todo in changed:
            print(f"{GREEN}Done{RST}    {format_todo(todo)}")
    for tid in already:
        print(f"{DIM}#{tid} already done{RST}")
    for tid in missing:
        print(f"{RED}Error:{RST} todo #{tid} not found", file=sys.stderr)

    if missing:
        sys.exit(1)


def cmd_delete(args) -> None:
    data = load()
    deleted, missing = [], []

    for tid in args.id:
        todo = find_todo(data["todos"], tid)
        if todo is None:
            missing.append(tid)
        else:
            deleted.append(dict(todo))
            data["todos"].remove(todo)

    if deleted:
        save(data)
        for todo in deleted:
            delete_attachments(todo)
            print(f"{RED}Deleted{RST} {format_todo(todo)}")
    for tid in missing:
        print(f"{RED}Error:{RST} todo #{tid} not found", file=sys.stderr)

    if missing:
        sys.exit(1)


def cmd_edit(args) -> None:
    if not args.text and not args.priority and not args.image:
        die("specify new text, -p LEVEL, and/or --image PATH")

    data = load()
    todo = find_todo(data["todos"], args.id)
    if todo is None:
        die(f"todo #{args.id} not found")

    if args.text:
        todo["text"] = " ".join(args.text)

    if args.priority:
        p = PRIORITY_ALIASES.get(args.priority.lower())
        if p is None:
            die(f"unknown priority '{args.priority}'")
        todo["priority"] = p

    if args.image:
        if "images" not in todo:
            todo["images"] = []
        todo["images"].append(attach_image(todo["id"], args.image))

    save(data)
    print(f"{CYAN}Edited{RST}  {format_todo(todo)}")


def cmd_show(args) -> None:
    data = load()
    todo = find_todo(data["todos"], args.id)
    if todo is None:
        die(f"todo #{args.id} not found")

    print(format_todo(todo))
    images = todo.get("images", [])
    if not images:
        print(f"{DIM}  No attachments.{RST}")
        return
    for i, img in enumerate(images, 1):
        added = img.get("added_at", "")
        print(f"  {DIM}[{i}] {img['path']}  {added}{RST}")
        show_image(img["path"])


def cmd_clear(args) -> None:
    data   = load()
    before = len(data["todos"])

    if getattr(args, "all", False):
        removed = list(data["todos"])
        data["todos"] = []
    else:
        removed = [t for t in data["todos"] if t["done"]]
        data["todos"] = [t for t in data["todos"] if not t["done"]]

    n = before - len(data["todos"])
    for todo in removed:
        delete_attachments(todo)
    save(data)
    label = "todo" if n == 1 else "todos"
    print(f"{DIM}Removed {n} {label}.{RST}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p   = argparse.ArgumentParser(prog="todo", description="Simple CLI todo manager")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    sp = sub.add_parser("add", help="add a new todo")
    sp.add_argument("text", nargs="+", help="todo text")
    sp.add_argument("-p", "--priority", metavar="LEVEL",
                    help="high / medium (default) / low")
    sp.add_argument("--image", metavar="PATH", help="attach an image file")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("list", aliases=["ls"], help="list todos")
    sp.add_argument("-a", "--all", action="store_true", help="include done todos")
    sp.add_argument("-p", "--priority", metavar="LEVEL", help="filter by priority")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("done", help="mark todo(s) as done")
    sp.add_argument("id", type=int, nargs="+", metavar="ID")
    sp.set_defaults(func=cmd_done)

    sp = sub.add_parser("delete", aliases=["rm"], help="delete todo(s)")
    sp.add_argument("id", type=int, nargs="+", metavar="ID")
    sp.set_defaults(func=cmd_delete)

    sp = sub.add_parser("edit", help="edit a todo's text, priority, or image")
    sp.add_argument("id", type=int, metavar="ID")
    sp.add_argument("text", nargs="*", help="new text (optional)")
    sp.add_argument("-p", "--priority", metavar="LEVEL", help="new priority")
    sp.add_argument("--image", metavar="PATH", help="attach an image file")
    sp.set_defaults(func=cmd_edit)

    sp = sub.add_parser("show", help="show todo details and inline image")
    sp.add_argument("id", type=int, metavar="ID")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("clear", help="remove done todos")
    sp.add_argument("-a", "--all", action="store_true",
                    help="remove all todos (including pending)")
    sp.set_defaults(func=cmd_clear)

    return p


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
