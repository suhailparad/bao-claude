# bao

A small desktop pet that floats on your macOS desktop and shows, live, what
[Claude Code](https://claude.com/claude-code) is doing: thinking, reading, typing,
running commands, waiting for you, asking for permission, or done. It plays a short
sound on the important moments, so you can look away while Claude works.

https://github.com/user-attachments/assets/4cb4add8-5b59-4418-be31-370bf4755566

Four characters are built in: a **panda** (the default, with soft chimes), a
**ginger cat** (with meows, chirps and a purr), a **penguin** (with peeps, squawks and a
happy little bray) and a colourful **hummingbird** (with chirps, twitters and a wing hum).
You can add your own without touching any code.

## Requirements

- macOS (the ready-made app), Linux (Ubuntu 22.04+, X11 or Wayland with XWayland) or
  Windows 10/11 (from source)
- Claude Code
- Python 3.10 or newer, for a source install

## Install the app (macOS)

**With Homebrew** (Apple silicon):

```bash
brew install --cask suhailparad/bao/bao
open -a Bao          # click Connect to link it to Claude Code
```

This also puts the `bao` command on your PATH. `brew upgrade` updates it, and
`brew uninstall bao` removes the app and its Claude Code hooks (`--zap` also deletes `~/.bao`).

**Or by hand:**

1. Download `Bao-<version>-<arch>.dmg` (`arm64` for Apple silicon, `x86_64` for Intel Macs),
   open it and drag **Bao** into **Applications**.
2. Open Bao from Applications. The app isn't notarized by Apple yet, so the first time
   macOS says it can't check it. On macOS 14 and earlier: **right-click Bao → Open → Open**.
   On macOS 15 and later: try to open it once, then *System Settings → Privacy & Security →
   Open Anyway*. Or, in Terminal: `xattr -dr com.apple.quarantine /Applications/Bao.app`.
3. Bao asks to **connect to Claude Code**. Click *Connect*: it adds its hooks to
   `~/.claude/settings.json`, keeps everything else and saves a backup as
   `settings.json.bak`. (Using the [plugin](#install-as-a-claude-code-plugin)? Skip this.)

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

## Install from source (macOS, Linux, Windows)

macOS and Linux:

```bash
git clone https://github.com/suhailparad/bao-claude.git
cd bao-claude
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

On **Ubuntu**, install the Qt runtime libraries and (for click-to-focus) `xdotool` first:

```bash
sudo apt install python3-venv libxcb-cursor0 libegl1 libxkbcommon-x11-0 xdotool
```

Windows (PowerShell):

```powershell
git clone https://github.com/suhailparad/bao-claude.git
cd bao-claude
py -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e .
```

Then connect it to Claude Code, either with the [plugin](#install-as-a-claude-code-plugin)
(`python -m bao link-plugin`), or by writing the hooks into your settings:

```bash
python -m bao install-hooks   # registers bao's hooks in ~/.claude/settings.json
python -m bao doctor          # checks that everything is set up
```

`install-hooks` backs up your settings to `~/.claude/settings.json.bak` first, only
adds its own entries, and is safe to run again. The hooks point at this venv's Python,
so if you move or recreate the venv, run `install-hooks` (or `link-plugin`) again.

That's it: the pet starts by itself the next time you start a Claude Code session, and
quits about 15 minutes after the last session ends.

## Install as a Claude Code plugin

The plugin replaces the *Connect* / `install-hooks` step on every OS. Claude Code adds
bao's hooks when you install it and removes them when you uninstall it, and
`~/.claude/settings.json` is never edited. You still need bao itself (the Mac app, or a
source install above), because the plugin doesn't contain it.

In Claude Code:

```
/plugin marketplace add suhailparad/bao-claude
/plugin install bao@bao
```

- **Bao.app:** nothing else to do, the plugin finds it in `/Applications` or `~/Applications`.
- **Source install:** tell the plugin which Python to use, from the activated venv:
  `python -m bao link-plugin` (writes `~/.bao/runtime`; run it again if you move the venv).

Then start a new Claude Code session. The plugin also adds a `pet` skill: ask Claude
things like "set up bao", "switch the pet to the penguin", "turn on quiet hours from
22:00 to 08:00" or "why isn't the panda reacting?".

The plugin's hook is a small `sh` script (Git Bash runs it on Windows). It finds bao in
this order: `$BAO_PYTHON`, the path in `~/.bao/runtime`, then Bao.app. If hooks from
`install-hooks` / *Connect* are still in `settings.json`, the plugin stays quiet so events
aren't sent twice; run `bao uninstall-hooks` to hand over to the plugin.

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

### Platform notes

| | macOS | Linux | Windows |
|---|---|---|---|
| Click to focus the terminal | exact Terminal/iTerm2 tab, other apps | the terminal window, via `xdotool` or `wmctrl` | the terminal window (Windows Terminal, VS Code, console) |
| `system:` sounds | `system:Glass` (/System/Library/Sounds) | `system:complete` (freedesktop theme) | `system:tada` (C:\Windows\Media) |
| Hook ↔ pet | Unix socket `~/.bao/pet.sock` | Unix socket | localhost TCP, port + token in `~/.bao/pet.port` |

On a Wayland desktop the pet runs through XWayland, because Wayland doesn't let apps
place their own windows (it couldn't remember its spot or wander). A see-through
window needs a compositor, which every mainstream Linux desktop has.

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
