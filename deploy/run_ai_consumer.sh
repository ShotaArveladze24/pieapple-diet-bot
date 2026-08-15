#!/bin/sh
# Runs the AI queue consumer once: hands ai_queue/CONSUMER_PROMPT.md to the Claude Code
# CLI in non-interactive print mode (billed to the logged-in Claude Pro subscription,
# not a metered API key) and lets it process pending files under data/ai_queue/ per
# ai_queue/SPEC.md. Scheduled every 5 minutes by pieapple-ai-consumer.timer - see
# CONFIGURATION.md for setup.
set -eu
cd "$(dirname "$0")/.."
claude -p "$(cat ai_queue/CONSUMER_PROMPT.md)"
