#!/bin/sh
# Runs the AI queue consumer once: hands ai_queue/CONSUMER_PROMPT.md to the Claude Code
# CLI in non-interactive print mode (billed to the logged-in Claude Pro subscription,
# not a metered API key) and lets it process pending files under data/ai_queue/ per
# ai_queue/SPEC.md. Scheduled every minute by pieapple-ai-consumer.timer - see
# CONFIGURATION.md for setup.
#
# Runs `claude` through a login shell (`bash -lc`) rather than invoking it directly:
# systemd services don't source ~/.bashrc/~/.profile, so a `claude` CLI whose PATH entry
# was only set up by nvm/npm in your login shell config would otherwise fail with
# "command not found" here even though it works fine over SSH. REPO_DIR is exported and
# re-applied inside the login shell in case its own startup files `cd` elsewhere.
set -eu
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export REPO_DIR
bash -lc 'cd "$REPO_DIR" && claude -p "$(cat ai_queue/CONSUMER_PROMPT.md)"'
