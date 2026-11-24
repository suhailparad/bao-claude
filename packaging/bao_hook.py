"""PyInstaller entry script for the Qt-free bao-hook helper (see bao.bundle.hook_main)."""

import sys

from bao.bundle import hook_main

sys.exit(hook_main())
