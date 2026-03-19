# -*- coding: utf-8 -*-
"""Allow running Taskbolt via ``python -m taskbolt``."""
from .cli.main import cli

if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
