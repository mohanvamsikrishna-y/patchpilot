"""Allow python -m patchpilot to use the same entry point as the installed CLI."""

from .cli import main

raise SystemExit(main())
