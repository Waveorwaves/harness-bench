# Image that agent, capture and evaluator containers run from. Built and used on Docker Desktop for macOS (about 6 GB).
#
#   docker build -t harness-bench:latest docker/
#
# Add or remove harnesses with --build-arg NPM_HARNESSES="...". Droid and Hermes ship their own
# installers rather than npm packages; add them below once you have confirmed the install steps.
FROM node:22-bookworm-slim

# chromium takes the screenshots for visual tasks; it renders WebGL in software, with no GPU.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 git ca-certificates curl ripgrep chromium fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
ENV HB_BROWSER=chromium \
    HB_BROWSER_FLAGS="--disable-gpu --use-angle=swiftshader --enable-unsafe-swiftshader --disable-dev-shm-usage"

ARG NPM_HARNESSES="@openai/codex @anthropic-ai/claude-code opencode-ai @earendil-works/pi-coding-agent @oh-my-pi/pi-coding-agent"
RUN npm install -g ${NPM_HARNESSES}

# Several harnesses refuse to run unattended as root.
RUN useradd --create-home bench
USER bench
