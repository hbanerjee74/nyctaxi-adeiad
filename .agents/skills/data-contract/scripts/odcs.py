"""The plugin's `odcs` launcher: the vibedata-odcs command with the Intent's sandbox resolved.

Everything the tool does lives in the `vibedata-odcs` package, pinned by the managed constraints.
This file adds only what the plugin knows and the package must not: which platform the Intent
runs on, and where that platform's sandbox is. Run it exactly as the package's `odcs` command:

  python3 odcs.py check | reverse | generate | diff <base-ref> | profile | export <format> --out DIR | results <file> | version
"""

import json
import sys
from pathlib import Path
from typing import TypedDict

# The plugin's own scripts, where the platform modules and the Intent-context reader live.
PLUGIN_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"

INSTALL = (
    "write the effective constraints with `python3 <plugin>/scripts/runtime_pins.py --out <scratch>/constraints.txt`, "
    "then run `python3 -m pip install -c <scratch>/constraints.txt -r <skill>/scripts/requirements.txt`"
)


class Destination(TypedDict, total=False):
    """What the resolver tells the package about the Intent's sandbox."""

    family: str
    path: str
    platform: str
    database: str
    host: str
    http_path: str


def plugin_destination(repo_map: dict) -> Destination | None:
    """What the plugin's platform module says the Intent's sandbox is; None outside a runtime."""
    if not (PLUGIN_SCRIPTS / "platforms").is_dir():
        return None
    if str(PLUGIN_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(PLUGIN_SCRIPTS))
    try:
        from intent_context import IntentContextError, load_intent_context
    except ImportError:  # no Intent-context reader beside this copy: the caller passes --catalog
        return None
    try:
        context = dict(load_intent_context())
    except (IntentContextError, OSError):  # no Intent context: the caller passes --catalog
        return None
    from platforms import UnknownPlatformError, load

    platform = context.get("VD_DOMAIN_DATA_PLATFORM") or str(repo_map.get("data_platform") or "")
    try:
        module = load(platform)
        destination = {**module.expected_destination(context), "platform": platform}
        # Coordinates only the plugin knows (a host, a name), read by the platform module from the context.
        return {**destination, **getattr(module, "engine_coordinates", lambda _context: {})(context)}
    except UnknownPlatformError:
        return {"platform": platform}


def run() -> None:
    try:
        from vibedata.odcs.cli import main
    except ImportError as error:  # absent, or installed without what this launcher needs
        print(json.dumps([{
            "severity": "error",
            "code": "cli/package-missing",
            "message": f"vibedata-odcs cannot be imported ({error}): {INSTALL}",
        }]))
        sys.exit(1)
    main(destination_resolver=plugin_destination)


if __name__ == "__main__":
    run()
