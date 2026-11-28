#!/usr/bin/env sh
set -eu
ROOT=$(git rev-parse --show-toplevel)
git -C "$ROOT" config core.hooksPath .githooks
echo "Installed repository hooks from .githooks"
