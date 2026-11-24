# bao — Implementation Plan

Decisions: **PySide6**, **sprite-pack characters** (panda by default), **one pet for all sessions (highest priority wins)**, **generated .wav sounds + macOS system sounds**.

## Milestone 1: Skeleton and event pipeline ✅ (done 2026-11-24)
- `pyproject.toml` (PySide6, dev: pytest, ruff), package layout, `python -m bao` CLI
- `hook.py`: read stdin JSON → send `{event, session_id, cwd, tool_name, notification_type, message, ts}` to the socket. Always exit 0.
- `ipc.py`: Unix socket server thread → Qt signal; single-instance lock
- `sessions.py`: per-session state machine + priority resolver, with unit tests
- `send` subcommand to simulate events
- **Done when:** `send thinking` changes the state printed in the log of a running app

## Milestone 2: Window and animation ✅ (done 2026-11-24)
- Frameless, translucent, always-on-top `PetWindow`, shown on all Spaces, no Dock icon (`LSUIElement`-style via `Qt.Tool`)
- Frame animator (QTimer per state fps, loop / one-shot with `next`), drag to move, position saved
- Speech bubble: state text plus project name, fades out after a few seconds (stays visible while waiting or needs permission)
- Right-click menu: Character ▸, Size ▸, Mute, Volume ▸, Quit
- **Done when:** the window animates through states as `send` events arrive
- Pulled forward from M3: `character.py` loader with fallbacks and validation, user character dir, and first-pass panda frames for all 12 animations

## Milestone 3: Sounds and panda polish ✅ (done 2026-11-24: sounds; panda polish ongoing as feedback comes in)
- `tools/gen_panda.py`: QPainter-drawn panda, ~6–12 frames per state:
  idle (breathing, blinking), greeting (wave), thinking (thought dots / scratching head),
  working (typing on a tiny laptop), reading, running, waiting (looking at you, tapping foot),
  needs_permission (raised paw, "!"), done (jump + confetti), compacting, sleeping (Zzz)
- `tools/gen_sounds.py`: short chimes for hello / waiting / alert / done / bye
- Manifest loader with fallbacks and validation, plus a user character dir
- **Done when:** the full panda set plays and the sounds respect mute and volume

## Milestone 4: Claude Code integration ✅ (done 2026-11-24, installed in ~/.claude/settings.json)
- `installer.py`: add hooks for SessionStart, UserPromptSubmit, PreToolUse, PostToolUse,
  Notification, Stop, SubagentStop, PreCompact, SessionEnd (backup, idempotent, uninstall)
- Auto-launch the pet on SessionStart. Go to sleep when idle; quit N minutes after the last session ends (configurable).
- `doctor` command
- **Done when:** opening `claude` makes the panda appear, and it follows a real session end to end

## Milestone 5: Polish and extensibility
- Remove the `claude_pet/` shim package (and its entry in `pyproject.toml`) once every Claude session started before the rename to Bao (2026-11-24) is closed
- Second sample character to prove the pack format (e.g. a cat, recoloured from the panda generator)
- Optional menu-bar tray icon, launch at login (optional)
- README with a "How to make a character" guide

## Risks / notes
- Hook latency: PreToolUse and PostToolUse fire on every tool call, so the hook must stay tiny (stdlib, no Qt import).
- macOS: transparent windows over full-screen apps need `Qt.WindowStaysOnTopHint` + `Qt.Tool`. Test this on Monterey.
- Notification input fields vary by Claude Code version. Parse defensively.
