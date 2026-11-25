---
name: pet
description: Set up, check and control the bao desktop pet that shows what Claude Code is doing. Use when the user mentions bao, "the pet", "the panda" (or cat, penguin, hummingbird), or asks to set it up, check why it isn't reacting, switch character, resize it, mute it or change its sounds, turn on Do Not Disturb or quiet hours, stop it wandering, hide the speech bubble, or quit it.
---

# bao desktop pet

The plugin's hooks send every Claude Code event to the bao pet app. The plugin does
**not** contain the app (it needs Qt), so a bao runtime must be installed on this Mac.
`${CLAUDE_PLUGIN_ROOT}/hooks/bao-hook` looks for one in this order and silently does
nothing if none is found:

1. `$BAO_PYTHON`: a python that has bao installed
2. `~/.bao/runtime`: one line, the path to such a python or to Bao.app's `bao-hook`
3. `/Applications/Bao.app` or `~/Applications/Bao.app`

## Find the `bao` command

Use the first one that works, and call it `BAO` below:
- Bao.app: `/Applications/Bao.app/Contents/MacOS/Bao -I -m bao` (or under `~/Applications`)
- the python named in `~/.bao/runtime`: `<python> -I -m bao`
- `bao` on PATH

If there is none, help the user install it:
- **App (recommended):** `brew install --cask suhailparad/bao/bao` (Apple silicon), or download
  the DMG from https://github.com/suhailparad/bao-claude/releases and drag Bao into Applications.
  Bao.app is found automatically. When Bao opens and offers to *Connect* to Claude Code, the
  plugin already does that, so it can be skipped. Connecting anyway doesn't cause duplicate events.
- **From source:** clone the repo, `python3 -m venv .venv && .venv/bin/pip install -e .`
  (Python 3.10+), then write the venv's python path (not symlink-resolved) to `~/.bao/runtime`:
  `echo "$PWD/.venv/bin/python" > ~/.bao/runtime`.

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
