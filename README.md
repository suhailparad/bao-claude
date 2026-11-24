# bao

A small desktop pet that floats on your macOS desktop and shows, live, what
[Claude Code](https://claude.com/claude-code) is doing: thinking, reading, typing,
running commands, waiting for you, asking for permission, or done. It plays a short
sound on the important moments, so you can look away while Claude works.

Four characters are built in: a **panda** (the default, with soft chimes), a
**ginger cat** (with meows, chirps and a purr), a **penguin** (with peeps, squawks and a
happy little bray) and a colourful **hummingbird** (with chirps, twitters and a wing hum).
You can add your own without touching any code.

## Requirements

- macOS (built and tested on macOS 12; other platforms aren't supported yet)
- Claude Code
- Python 3.10 or newer, only if you install from source

## Install the app

1. Download `Bao-<version>-<arch>.dmg` (`arm64` for Apple silicon, `x86_64` for Intel Macs),
   open it and drag **Bao** into **Applications**.
2. Open Bao from Applications. The app isn't notarized by Apple yet, so the first time
   macOS says it can't check it: **right-click Bao → Open → Open** (on macOS 13 and later,
   if there's no Open button: *System Settings → Privacy & Security → Open Anyway*).
3. Bao asks to **connect to Claude Code**. Click *Connect*: it adds its hooks to
   `~/.claude/settings.json`, keeps everything else and saves a backup as
   `settings.json.bak`.

That's it: the pet appears whenever you start a Claude Code session, and quits about 15
minutes after the last one ends. There's no Dock icon; right-click the pet for its menu.

If you move Bao.app somewhere else, open it once more and it offers to update the hooks.

**Command line (optional).** The app binary is also the `bao` command:

```bash
sudo ln -sf /Applications/Bao.app/Contents/MacOS/Bao /usr/local/bin/bao
bao doctor          # bao status, bao dnd on, bao send thinking, ... as below
```

**Uninstall.** Run `/Applications/Bao.app/Contents/MacOS/Bao uninstall-hooks`, quit the
pet (right-click → Quit Bao), then delete Bao.app and `~/.bao`.

## Install from source

```bash
git clone https://github.com/suhailparad/bao-claude.git
cd bao-claude
python -m venv .venv && source .venv/bin/activate
pip install -e .

python -m bao install-hooks   # registers bao's hooks in ~/.claude/settings.json
python -m bao doctor          # checks that everything is set up
```

`install-hooks` backs up your settings to `~/.claude/settings.json.bak` first, only
adds its own entries, and is safe to run again. The hooks point at this venv's Python,
so if you move or recreate the venv, run `install-hooks` again.

That's it: the pet starts by itself the next time you start a Claude Code session, and
quits about 15 minutes after the last session ends.

## What the pet shows

| Claude Code is… | The pet | Sound |
|---|---|---|
| starting a session | waves hello | hello |
| thinking about your prompt | thinks | – |
| reading / searching files | reads | – |
| editing / writing files | types | – |
| running a command | runs | – |
| asking for permission | asks for your attention | alert |
| waiting for your input | waits | waiting |
| finished its turn | celebrates | done |
| compacting the conversation | squishes down, with sparkles | – |
| ending the session | falls asleep | bye |

When Claude finishes, the bubble says how long the turn took ("Bao finished in 4m 12s!", then
"took 4m 12s" while it waits for you), so you know at a glance whether it's worth looking.

If a permission request goes unanswered for a minute, the pet shakes and plays the alert
once more (turn this off in the right-click menu, or set `permission_reminder_seconds`).

With several Claude Code sessions open there's still one pet. It shows the most
urgent state (permission first, then waiting, then done, and so on), and the speech
bubble says how many sessions there are. Click the pet to jump to the session it's showing;
`python -m bao status` lists every session with its project.

## Using it

- **Drag** the pet anywhere. It remembers where you put it.
- While Claude is idle or waiting for you, the pet **wanders around**: the panda, cat and
  penguin waddle left and right, the hummingbird flies about. As soon as Claude gets to
  work it hurries back to the spot you gave it. Turn it off with *Wander around when idle*.
- **Click** the pet to jump to the terminal of the session it's showing. In Terminal and
  iTerm2 it picks the exact tab (macOS asks once to let bao control the app); in other
  apps (VS Code, Ghostty, WezTerm, Warp, …) it brings the app to the front.
- **Right-click** it to pick a character, change its size, mute or set the volume,
  turn single sounds off, hide the speech bubble, or quit.

From the terminal:

```bash
python -m bao run              # start the pet by hand
python -m bao status           # what the pet is showing, and every session it knows
python -m bao send thinking    # try a state (start, reading, typing, running, permission,
                               #   waiting, done, compact, end, …)
python -m bao sound done       # play a cue through the running pet
python -m bao dnd on           # Do Not Disturb: no sounds (off | status)
python -m bao quit
python -m bao uninstall-hooks  # remove bao's hooks from Claude Code
```

**Do Not Disturb** (right-click menu or `bao dnd on`) silences every sound but keeps the
animations; a small moon shows while it's on. Set `"quiet_hours": ["22:00", "08:00"]` in the
config to turn it on automatically every day (the range may cross midnight).

Settings live in `~/.bao/config.json` (character, scale, muted, volume, muted_cues,
show_bubble, roam, permission_reminder_seconds, do_not_disturb, quiet_hours, quit_after_minutes,
position) and the log in `~/.bao/pet.log`.

## Make your own character

A character is just a folder with a `manifest.json`, PNG frames and sounds. Put it in
`~/.bao/characters/<id>/` (a folder with the same `id` as a built-in one replaces it):

```
~/.bao/characters/fox/
  manifest.json
  frames/idle/000.png, 001.png, ...
  frames/thinking/000.png, ...
  sounds/hello.wav, done.wav, ...
```

```json
{
  "id": "fox", "name": "Fox", "version": 1,
  "size": [160, 160],
  "states": {
    "idle":     {"frames": "frames/idle",     "fps": 6, "loop": true},
    "thinking": {"frames": "frames/thinking", "fps": 8, "loop": true},
    "done":     {"sheet": "sheets/done.png", "frame_size": [160, 160], "count": 12,
                 "fps": 12, "loop": false, "next": "waiting"}
  },
  "sounds": {"hello": "sounds/hello.wav", "done": "system:Glass"},
  "roam": {"style": "walk", "speed": 36, "faces": "front"},
  "fallback_state": "idle"
}
```

- States: `idle`, `greeting`, `thinking`, `working` (plus `reading`, `typing`, `running`),
  `needs_permission`, `waiting`, `done`, `compacting`, `sleeping`. Any you leave out
  fall back to `fallback_state`. The tool variants fall back to `working` first.
- Frames can be a folder of numbered PNGs or one sprite sheet.
- Wandering: a `roaming` state is played while the pet walks or flies. `roam` (optional)
  sets the `style` (`walk` along the ground or `fly` in the air), the `speed` in px/s
  and which way the art `faces` (`front`, or `left`/`right` to mirror it toward travel).
- Sound cues: `hello`, `waiting`, `alert`, `done`, `bye`. Use a `.wav` file in the
  folder, or `"system:<Name>"` for a macOS sound such as `system:Glass`.
- A broken character is skipped (and logged), so it can't crash the pet. Run
  `python -m bao doctor` to see what loaded.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff format && ruff check

python tools/gen_panda.py                    # regenerate the panda's frames
python tools/gen_cat.py                      # regenerate the cat's frames
python tools/gen_penguin.py                  # regenerate the penguin's frames
python tools/gen_hummingbird.py              # regenerate the hummingbird's frames
python tools/gen_sounds.py                   # regenerate the panda's chimes
python tools/gen_sounds.py --character cat   # regenerate the cat's meows
python tools/gen_sounds.py --character penguin  # regenerate the penguin's peeps
python tools/gen_sounds.py --character hummingbird  # regenerate the hummingbird's chirps
```

### Building Bao.app

```bash
pip install -e ".[app]"         # adds PyInstaller
packaging/build_mac.sh          # → dist/Bao.app and dist/Bao-<version>-<arch>.dmg
packaging/build_mac.sh --no-dmg # app only
```

The build is for the Mac's own architecture (build on an Intel Mac for `x86_64`). The app
holds two executables: `Bao` (the pet and CLI; it accepts `-I -m bao …` like the venv's
Python, so the hook's launcher and `doctor` work unchanged) and `bao-hook`, a Qt-free
helper the hooks run, because PyInstaller's PySide6 setup would add ~100 ms to every
hook call. The icon comes from `tools/gen_icon.py`.

The built-in art and sounds are generated by these scripts (QPainter and the standard
library), so change the scripts rather than the PNG or WAV files. See
[CLAUDE.md](CLAUDE.md) for the architecture and conventions.

### How it works

Claude Code runs `bao.hook` on each hook event. The hook is standard-library only,
always exits 0 and finishes in well under 300 ms, so it can never slow down or break
Claude. It forwards the event as one JSON line over a Unix socket (`~/.bao/pet.sock`)
to the pet app (PySide6), and starts the app on `SessionStart` if it isn't running.
