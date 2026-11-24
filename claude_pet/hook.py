"""Old hook entry point (``-m claude_pet.hook``). Forwards to ``bao.hook``; always exits 0."""

import sys

try:
    from bao.hook import main

    main()
except Exception:
    pass
sys.exit(0)
