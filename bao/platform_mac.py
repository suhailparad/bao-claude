"""Small macOS-only tweaks via pyobjc. Every function is a safe no-op elsewhere."""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

IS_MAC = sys.platform == "darwin"


def hide_dock_icon() -> None:
    """Run as an accessory app: no Dock icon, no menu bar takeover."""
    if not IS_MAC:
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception as exc:  # pyobjc missing or API changed
        log.info("could not hide Dock icon: %s", exc)


def float_on_all_spaces(win_id: int) -> None:
    """Keep the pet visible on every Space and above full-screen apps."""
    if not IS_MAC:
        return
    try:
        import objc
        from AppKit import (
            NSFloatingWindowLevel,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorStationary,
        )

        view = objc.objc_object(c_void_p=win_id)
        window = view.window()
        if window is None:
            return
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )
        window.setLevel_(NSFloatingWindowLevel)
        window.setHidesOnDeactivate_(False)
        window.setHasShadow_(False)
    except Exception as exc:
        log.info("could not configure window for all Spaces: %s", exc)
