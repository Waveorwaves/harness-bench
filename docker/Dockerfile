# Image that agent, capture and evaluator containers run from. Built and used on Docker Desktop for macOS (about 6 GB).
#
#   docker build -t harness-bench:latest docker/
#
# Add or remove npm-packaged harnesses with --build-arg NPM_HARNESSES="...". Droid and Hermes ship their
# own installers instead; each is fetched from the vendor's own address, named in an ARG below.
FROM node:22-bookworm-slim

# chromium takes the screenshots for visual tasks; it renders WebGL in software, with no GPU.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 git ca-certificates curl ripgrep chromium fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
ENV HB_BROWSER=chromium \
    HB_BROWSER_FLAGS="--disable-gpu --use-angle=swiftshader --enable-unsafe-swiftshader --disable-dev-shm-usage"

ARG NPM_HARNESSES="@openai/codex @anthropic-ai/claude-code opencode-ai @earendil-works/pi-coding-agent @oh-my-pi/pi-coding-agent"
RUN npm install -g ${NPM_HARNESSES}

# omp runs on Bun rather than Node.
RUN npm install -g bun

ARG DROID_INSTALLER=https://app.factory.ai/cli
RUN curl -fsSL "$DROID_INSTALLER" | sh \
    && install -m 755 /root/.local/bin/droid /usr/local/bin/droid && rm /root/.local/bin/droid

# Several harnesses refuse to run unattended as root.
RUN useradd --create-home bench

# Hermes keeps its program files and its settings in one folder (HERMES_HOME) and must be able to write
# there, so it is installed by the unprivileged user into /opt/hermes and left writable for whichever
# user a run uses. Nothing written there outlives a run: every run starts from this image again.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 xz-utils unzip \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -o bench -g bench /opt/hermes
COPY --chmod=755 hermes-launcher /usr/local/bin/hermes
ARG HERMES_INSTALLER=https://hermes-agent.nousresearch.com/install.sh
USER bench
ENV HERMES_HOME=/opt/hermes
RUN curl -fsSL "$HERMES_INSTALLER" -o /tmp/hermes-install.sh \
    && bash /tmp/hermes-install.sh --skip-setup --skip-browser \
    && rm /tmp/hermes-install.sh \
    && chmod -R a+rwX /opt/hermes

# Devin's command-line tool, from its own installer. The installer ends by asking to log in, which
# fails here on purpose: each run brings its own login. The check after it is what must succeed.
USER root
ARG DEVIN_INSTALLER=https://cli.devin.ai/install.sh
RUN mkdir -p /opt/devin \
    && curl -fsSL "$DEVIN_INSTALLER" -o /tmp/devin-install.sh \
    && (HOME=/opt/devin bash /tmp/devin-install.sh || true) \
    && test -x /opt/devin/.local/share/devin/cli/_versions/current/bin/devin \
    && ln -s /opt/devin/.local/share/devin/cli/_versions/current/bin/devin /usr/local/bin/devin \
    && chmod -R a+rX /opt/devin && rm /tmp/devin-install.sh
USER bench

# Droid once more, to carry its current release. It is refreshed here, at the end, and not in the layer
# above: rebuilding that one would reinstall everything after it and move the other harnesses' pinned versions.
USER root
ARG DROID_REFRESHED=2026-10-07
RUN curl -fsSL "$DROID_INSTALLER" | sh \
    && install -m 755 /root/.local/bin/droid /usr/local/bin/droid && rm /root/.local/bin/droid
USER bench

# DeepSeek Harness's command-line tool: the same packages its desktop app runs, published on npm. Added at the
# end for the same reason as the layer above. Each run brings its own model settings and login.
USER root
ARG DSH_VERSION=0.2.0-rc.2
RUN npm install -g "@deepseek-ai/dsh@$DSH_VERSION" && dsh --version
USER bench
