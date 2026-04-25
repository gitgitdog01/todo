#!/usr/bin/env python3
"""CLI todo manager — stdlib only."""

import json
import os
import sys
import argparse
import tempfile
from datetime import datetime
from pathlib import Path

DATA_DIR  = Path.home() / ".local" / "share" / "todo"
DATA_FILE = DATA_DIR / "todos.json"

PRIORITY_ALIASES = {
    "high": "HIGH",   "h": "HIGH",
    "medium": "MEDIUM", "med": "MEDIUM", "m": "MEDIUM",
    "low": "LOW",     "l": "LOW",
}
PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# ── ANSI ──────────────────────────────────────────────────────────────────────

_color = "NO_COLOR" not in os.environ and sys.stdout.isatty()

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
    return f"  {num}  {marker}  {check}{text}"

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
    }
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
            print(f"{RED}Deleted{RST} {format_todo(todo)}")
    for tid in missing:
        print(f"{RED}Error:{RST} todo #{tid} not found", file=sys.stderr)

    if missing:
        sys.exit(1)


def cmd_edit(args) -> None:
    if not args.text and not args.priority:
        die("specify new text and/or -p LEVEL")

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

    save(data)
    print(f"{CYAN}Edited{RST}  {format_todo(todo)}")


def cmd_clear(args) -> None:
    data   = load()
    before = len(data["todos"])

    if getattr(args, "all", False):
        data["todos"] = []
    else:
        data["todos"] = [t for t in data["todos"] if not t["done"]]

    n = before - len(data["todos"])
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

    sp = sub.add_parser("edit", help="edit a todo's text or priority")
    sp.add_argument("id", type=int, metavar="ID")
    sp.add_argument("text", nargs="*", help="new text (optional)")
    sp.add_argument("-p", "--priority", metavar="LEVEL", help="new priority")
    sp.set_defaults(func=cmd_edit)

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
