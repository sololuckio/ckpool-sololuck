#!/usr/bin/env bash
# Clone upstream ckpool at the pinned commit, apply SoloLuck's patches, and
# print the resulting git tree hash so you can compare it against the one in
# README.md. Optionally builds.
#
#   ./apply.sh              # clone + apply + print tree hash
#   ./apply.sh --build      # also ./autogen.sh && ./configure && make
#   ./apply.sh --dir /tmp/x # work somewhere other than ./ckpool
#
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

UPSTREAM="https://bitbucket.org/ckolivas/ckpool.git"
PIN="2e44101e2da2c11f499be76d16e6a26cd95cfea7"     # v1.2.0
EXPECT_TREE="d58aef465a30d56cf6d1d883e4a8e5889180b5d9"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="$HERE/ckpool"
DO_BUILD=0

while [ $# -gt 0 ]; do
  case "$1" in
    --build) DO_BUILD=1; shift ;;
    --dir)   WORKDIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -e "$WORKDIR" ]; then
  echo "refusing to touch existing path: $WORKDIR" >&2
  echo "remove it, or pass --dir somewhere empty." >&2
  exit 1
fi

echo "==> cloning ckpool"
git clone --quiet "$UPSTREAM" "$WORKDIR"
cd "$WORKDIR"

echo "==> checking out v1.2.0 ($PIN)"
git checkout --quiet "$PIN"

# git am needs an identity; use a local one so it never touches global config.
git config user.name  "ckpool-sololuck apply.sh"
git config user.email "apply@localhost"

echo "==> applying $(ls "$HERE"/patches/*.patch | wc -l) patches"
git am "$HERE"/patches/*.patch

TREE="$(git rev-parse 'HEAD^{tree}')"
echo
echo "==> resulting tree: $TREE"
if [ "$TREE" = "$EXPECT_TREE" ]; then
  echo "==> MATCH. This is byte-for-byte the tree the patches describe."
else
  echo "==> MISMATCH. Expected $EXPECT_TREE" >&2
  echo "    Something differs. Do not trust this tree." >&2
  exit 1
fi

echo
git --no-pager diff --stat "$PIN"..HEAD

if [ "$DO_BUILD" = 1 ]; then
  echo
  echo "==> building"
  ./autogen.sh
  ./configure
  make -j"$(nproc 2>/dev/null || echo 2)"
  echo "==> built. Binaries are in $WORKDIR/src"
fi

echo
echo "Source at $WORKDIR"
echo "Note: this proves what the source says. It does not prove which binary"
echo "sololuck.io runs. Nobody should accept that it does."
