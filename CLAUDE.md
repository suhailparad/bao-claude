# CLAUDE.md — bao

A desktop pet (default: **panda**) that floats on the macOS desktop and shows, live,
what Claude Code is doing: thinking, working, waiting for input, needs permission,
done. It plays a sound on important events and supports multiple, swappable characters.

## Tech stack
- Python **3.10+** (dev machine: 3.10.13 via pyenv, macOS 12 Monterey)
- **PySide6** (Qt 6) for the frameless, transparent, always-on-top window, animation and audio (`QSoundEffect`)
- The hook script (`bao/hook.py`) uses the **standard library only** so it starts fast and never breaks Claude
- Asset generators (`tools/`) use QPainter (no Pillow needed) and the stdlib `wave` module

## Architecture

```
Claude Code ──(hook JSON on stdin)──► hook.py ──(JSON line over Unix socket)──► pet app (Qt)
                                         │                                        │
                                         └─ spawns pet app on SessionStart        ├─ SessionTracker (state per session_id)
                                            if it isn't running                    ├─ StateResolver (priority → one shown state)
                                                                                   ├─ Character (manifest + frames + sounds)
                                                                                   ├─ PetWindow (animation, bubble, drag, menu)
                                                                                   └─ SoundPlayer (mute/volume)
```

- **IPC:** Unix stream socket at `~/.bao/pet.sock`, one JSON object per line.
  The hook connects with a ~200 ms timeout. If the pet isn't there, it drops the event
  (and launches the pet only for `SessionStart`).
- **Hook golden rule:** `hook.py` must **always exit 0, print nothing to stdout, and finish in under 300 ms**.
  Anything else can block or confuse Claude Code. Wrap everything in try/except.
- **Single instance:** the pet app holds `~/.bao/pet.lock`. A second launch exits quietly.

### Event → state mapping
| Claude Code hook | Pet state | Sound |
|---|---|---|
| `SessionStart` | `greeting` → `idle` | `hello` |
| `UserPromptSubmit` | `thinking` | – |
| `PreToolUse` | `working` (variant by tool: `reading` Read/Grep/Glob, `typing` Edit/Write, `running` Bash) | – |
| `PostToolUse` | `thinking` | – |
| `Notification` (permission prompt) | `needs_permission`; unanswered for `permission_reminder_seconds` (60) → shake + `alert` once more | `alert` |
| `Notification` (idle / waiting for input) | `waiting` | `waiting` |
| `Stop` | `done` (celebrate ~3 s, bubble "Done in 4m 12s!" = time since `UserPromptSubmit`) → `waiting` | `done` |
| `SubagentStop` | unchanged | – |
| `PreCompact` | `compacting` | – |
| `SessionEnd` | remove session; `sleeping` if none left, quit after idle timeout | `bye` |
| (no events for N min) | `sleeping` | – |

On `SessionStart`/`UserPromptSubmit` the hook also sends `terminal` (`__CFBundleIdentifier` and
the tty found by walking parent processes with `ps`, ≤ 80 ms) so a click on the pet can focus it.

Use the `notification_type` field of the Notification input when it's there. Otherwise fall back to matching the `message` text.

### Multi-session: one pet, highest priority wins
Priority: `needs_permission > waiting > done > working > thinking > compacting > greeting > idle > sleeping`.
When priorities tie, the most recent event wins. The speech bubble shows the state text plus the project name (basename of `cwd`).

## Characters (sprite packs)
Each character is a folder; adding one means adding a folder, with **no code changes**.

```
bao/characters/<id>/
  manifest.json
  frames/<state>/000.png, 001.png, ...   (or a sprite sheet: see manifest)
  sounds/*.wav
```

`manifest.json`:
```json
{
  "id": "panda", "name": "Panda", "version": 1,
  "size": [160, 160],
  "states": {
    "idle":     {"frames": "frames/idle",     "fps": 6,  "loop": true},
    "thinking": {"frames": "frames/thinking", "fps": 8,  "loop": true},
    "done":     {"sheet": "sheets/done.png", "frame_size": [160,160], "count": 12, "fps": 12, "loop": false, "next": "waiting"}
  },
  "sounds": {"hello": "sounds/hello.wav", "done": "sounds/done.wav", "alert": "sounds/alert.wav",
             "waiting": "sounds/waiting.wav", "bye": "sounds/bye.wav"},
  "fallback_state": "idle"
}
```
- Any state missing from a manifest falls back to `fallback_state`. A tool variant (e.g. `typing`) falls back to `working`, then to `fallback_state`.
- Sound values can also be `"system:Glass"`, which plays `/System/Library/Sounds/Glass.aiff`.
- Validate manifests on load. A broken character logs an error and is skipped; it must never crash the app.
- User characters can also live in `~/.bao/characters/` and override the built-in ones by `id`.

## Project layout (target)
```
bao/
  __main__.py        # CLI: run | send | status | sound | dnd | quit | install-hooks | uninstall-hooks | doctor
  doctor.py          # setup checks
  focus.py           # click → focus the session's terminal (bundle id + tty, AppleScript/open -b)
  hook.py            # stdlib-only hook entry point
  paths.py           # ~/.bao/* locations (BAO_HOME overrides; stdlib only)
  ipc.py             # Unix-socket client/server + single-instance lock (stdlib only)
  app.py             # Qt app: PetController (GUI thread) wiring IPC → tracker → window/sound
  sessions.py        # SessionTracker + StateResolver (pure Python, unit-tested)
  character.py       # manifest loading/validation, frame loading
  window.py          # PetWindow: transparent frameless widget, animation, bubble, drag, context menu
  platform_mac.py    # pyobjc tweaks: hide Dock icon, float on all Spaces (no-ops elsewhere)
  sound.py           # SoundPlayer: .wav → QSoundEffect, system:/aiff/mp3 → afplay; mute, volume, per-cue off, DND/quiet hours, 1.5 s repeat guard
  config.py          # ~/.bao/config.json (character, scale, muted, volume, muted_cues, show_bubble, permission_reminder_seconds,
                     #   do_not_disturb, quiet_hours, position)
  installer.py       # merge/remove hooks in ~/.claude/settings.json (with backup)
  characters/panda/  # default character
  characters/cat/    # ginger tabby (same poses/props as the panda)
tools/
  gen_panda.py       # draws placeholder panda frames with QPainter (poses, props, generate())
  gen_cat.py         # draws the cat with the panda's poses/props
  gen_sounds.py      # synthesizes .wav cues: panda chimes, cat meows/purr
tests/
```

## Commands
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m bao run                         # start the pet
python -m bao send thinking               # simulate an event (aliases: start thinking reading typing running
                                          #   working tool-done permission waiting done compact end)
python -m bao status                      # JSON of what the pet shows + all sessions
python -m bao sound done                  # play a cue through the running pet (respects mute)
python -m bao dnd on                      # Do Not Disturb: silence sounds (off | status)
python -m bao quit
python -m bao install-hooks               # register hooks in ~/.claude/settings.json (backs it up first)
python -m bao uninstall-hooks             # both accept --settings PATH (use a copy when testing!)
python -m bao doctor                      # check characters, config, hooks, running app

python tools/gen_panda.py                 # regenerate panda frames
python tools/gen_cat.py                   # regenerate cat frames
python tools/gen_sounds.py                # regenerate panda chimes (--character cat: cat meows)
pytest
```

## Conventions
- Keep `sessions.py`, `character.py` (manifest parsing) and `installer.py` free of Qt so they can be unit-tested.
- Only the Qt main thread touches widgets. The socket server pushes events in through a Qt signal.
- `installer.py` must be idempotent. It identifies its own hook entries by the command containing `bao.hook` and never touches other hooks.
  Always write `~/.claude/settings.json.bak` before changing anything.
- Hook commands use the venv's absolute python path (not symlink-resolved) with `-I`, so they work
  from any cwd and a project's own files can't shadow our modules. Moving the venv → re-run install-hooks.
- Never test the installer against the real `~/.claude/settings.json`: pass `--settings` with a copy.
- The app quits `quit_after_minutes` (config, default 15, 0 = never) after the last session ends;
  the next SessionStart relaunches it. A manual `run` with no sessions never auto-quits.
- User state lives in `~/.bao/` only: config, socket, lock, log (`pet.log`). Nothing goes in the repo.
- The app takes ~1.5 s to start (Qt import). The hook passes the event that triggered a launch via
  `run --initial-event`, so nothing is lost. Scripts that drive the app must wait for `pet.sock` to exist.
- Tests set `BAO_HOME` to a short dir under `/tmp`, because macOS limits Unix socket paths to ~104 bytes.
- The panda PNGs are generated: edit `tools/gen_panda.py`, never the PNGs by hand
  (`--sheet out.png` writes a contact sheet so you can review every frame at once).
- To check UI changes visually, render off-screen (`QT_QPA_PLATFORM=offscreen`, `PetWindow.grab()`).
  `screencapture` from a terminal without Screen Recording permission shows only the wallpaper.
- Keep black art readable on dark desktops: black shapes get a grey edge (`FUR_EDGE`).
- Sounds are generated too: edit `tools/gen_sounds.py` (it owns the manifest's `"sounds"` section;
  `gen_panda.py` keeps that section untouched).
- Type hints everywhere. Format with `ruff format` and lint with `ruff check`.
- macOS first. Keep platform-specific code (window flags, system sounds) behind small helpers so Linux and Windows can be added later.
