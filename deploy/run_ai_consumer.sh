#!/bin/sh
# Runs the AI queue consumer once: hands ai_queue/CONSUMER_PROMPT.md to the Claude Code
# CLI in non-interactive print mode (billed to the logged-in Claude Pro subscription,
# not a metered API key) and lets it process pending files under data/ai_queue/ per
# ai_queue/SPEC.md. Scheduled every minute by pieapple-ai-consumer.timer - see
# CONFIGURATION.md for setup.
#
# CLAUDE_BIN is the absolute path to the claude CLI. systemd services don't source
# ~/.bashrc/~/.profile, and even a login shell (bash -lc) typically no-ops ~/.bashrc for
# non-interactive shells (the standard Debian ~/.bashrc bails out on `case $- in *i*)`),
# so a PATH entry set up there - e.g. by nvm, or an npm global prefix under $HOME like
# ~/.npm-global/bin - is invisible here no matter how it's invoked. Resolving by full
# path instead sidesteps PATH/shell-startup-file behavior entirely. Override by setting
# CLAUDE_BIN in the environment (or via Environment= in the systemd unit) if claude
# lives somewhere else on your system - find it with `which claude` over SSH.
set -eu
cd "$(dirname "$0")/.."
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.npm-global/bin/claude}"
"$CLAUDE_BIN" -p "$(cat ai_queue/CONSUMER_PROMPT.md)"
