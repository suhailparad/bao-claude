---
name: pet
description: Set up, check and control the bao desktop pet that shows what Claude Code is doing. Use when the user mentions bao, "the pet", "the panda" (or cat, penguin, hummingbird), or asks to set it up, check why it isn't reacting, switch character, resize it, mute it or change its sounds, turn on Do Not Disturb or quiet hours, stop it wandering, hide the speech bubble, or quit it.
---

# bao desktop pet

The plugin's hooks send every Claude Code event to the bao pet app. It runs on macOS,
Linux and Windows. The plugin does **not** contain the app (it needs Qt), so bao must be
installed on this computer. `${CLAUDE_PLUGIN_ROOT}/hooks/bao-hook` (run with `sh`, so Git Bash
on Windows) looks for it in this order and silently does nothing if none is found:

1. `$BAO_PYTHON`: a python that has bao installed
2. `~/.bao/runtime`: one line, the path to such a python or to Bao.app's `bao-hook`
   (written by `bao link-plugin`)
3. macOS only: `/Applications/Bao.app` or `~/Applications/Bao.app`

## Find the `bao` command

Use the first one that works, and call it `BAO` below:
- the python named in `~/.bao/runtime`: `<python> -I -m bao`
- macOS Bao.app: `/Applications/Bao.app/Contents/MacOS/Bao -I -m bao` (or under `~/Applications`)
- `bao` on PATH

If there is none, help the user install it (see the bao README for details):
- **macOS, app (recommended):** `brew install --cask suhailparad/bao/bao` (Apple silicon), or the
  DMG from https://github.com/suhailparad/bao-claude/releases. Bao.app is found automatically;
  when it offers to *Connect* to Claude Code, that can be skipped (the plugin does it).
- **Linux / Windows / macOS from source:** clone https://github.com/suhailparad/bao-claude,
  create a venv (Python 3.10+) and `pip install -e .` in it. On Ubuntu first
  `sudo apt install python3-venv libxcb-cursor0 libegl1 libxkbcommon-x11-0 xdotool`.
  Then run `<venv python> -m bao link-plugin`, which writes `~/.bao/runtime`. The venv python is
  `.venv/bin/python`, or `.venv\Scripts\python.exe` on Windows. Don't write that file with
  PowerShell's `>` (it writes UTF-16).

## Check it works

Run `BAO doctor`. Two things to know when reading it:
- With the plugin, **"hooks not installed in settings.json" is expected**: the plugin provides them.
- If `settings.json` *does* contain bao hooks (from an older `bao install-hooks`), the plugin's
  hook stands down so events aren't counted twice. Suggest `BAO uninstall-hooks` to let the plugin
  take over. Never edit `~/.claude/settings.json` by hand for this.

Then `BAO status` shows what the pet displays. If the app isn't running, it starts with the next
Claude Code session, or start it now in the background: `BAO run`.

## Control it

| User wants | Do |
|---|---|
| Silence sounds for a while | `BAO dnd on` (`off`, `status`) |
| Hear a cue | `BAO sound done` (`hello`, `waiting`, `alert`, `bye`) |
| See it react | `BAO send thinking` (also `reading typing running permission waiting done compact end`) |
| Stop the pet | `BAO quit` |

Everything else lives in `~/.bao/config.json` (create it if missing, keep unknown keys):

| Key | Meaning |
|---|---|
| `character` | `panda`, `cat`, `penguin`, `hummingbird`, or a folder id in `~/.bao/characters/` |
| `scale` | size, e.g. `0.75`, `1.0`, `1.5` |
| `muted`, `volume` | all sound off; volume 0.0–1.0 |
| `muted_cues` | e.g. `["hello", "bye"]` |
| `show_bubble` | speech bubble on/off |
| `roam` | wander while idle |
| `quiet_hours` | `["22:00", "08:00"]` daily Do Not Disturb |
| `permission_reminder_seconds` | re-alert about an unanswered permission prompt (0 = off) |
| `quit_after_minutes` | quit after the last session ends (0 = never) |

Most of these are also in the pet's right-click menu. The app reads the file at startup,
so after editing it run `BAO quit` and then `BAO run` in the background.

## Making a new character

Characters are folders with a `manifest.json`, frames and sounds, placed in
`~/.bao/characters/<id>/`. See the "Make your own character" section of the bao README.
