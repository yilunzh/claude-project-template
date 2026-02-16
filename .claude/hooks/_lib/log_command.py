#!/usr/bin/env python3
"""Log slash command invocation as a metric.

Usage from command markdown files:
  .venv/bin/python3 .claude/hooks/_lib/log_command.py "arch-review"

Logs one entry with trigger="manual" to hook-metrics.jsonl.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from hook_utils import log_metric


def main():
    if len(sys.argv) < 2:
        print("Usage: log_command.py <command-name>", file=sys.stderr)
        sys.exit(1)

    command_name = sys.argv[1]
    log_metric(command_name, "run", trigger="manual", decision="allow")


if __name__ == "__main__":
    main()
