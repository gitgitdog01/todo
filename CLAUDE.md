# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A CLI todo manager written in Python 3.12 (stdlib only, no external dependencies).

- Entry point: `todo.py` (symlinked as `todo` at `~/.local/bin/todo`)
- Data store: `~/.local/share/todo/todos.json`

## Running

```bash
python3 todo.py <command> [args]
# or, via symlink:
todo <command> [args]
```

Commands: `add`, `list`, `done`, `delete`, `edit`, `clear`

## Design constraints

- No external dependencies — stdlib only.
- Priority levels: `HIGH` (`!!!`) > `MEDIUM` (`!`) > `LOW` (`·`)
- ANSI color output; respect the `NO_COLOR` environment variable.
