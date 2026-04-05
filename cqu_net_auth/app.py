"""CLI bootstrap and process-level runtime setup."""

import signal
import sys
import urllib.request

from cqu_net_auth.cli import parse_args
from cqu_net_auth.core.loop import run_loop


# Avoid inheriting system proxy settings that may hijack local portal requests.
urllib.request.getproxies = lambda: {}


def main():
    """Parse config and start the authentication loop."""
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))

    config = parse_args()
    run_loop(config)


if __name__ == "__main__":
    main()
