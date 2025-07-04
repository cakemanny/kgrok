#!/usr/bin/env bash
#
# This script is used in the docker image build workflow
#
# shellcheck disable=SC2001

set -xeuo pipefail

test -n "$GITHUB_REF"
test -n "$GITHUB_REF_NAME"

case "$GITHUB_REF" in
    refs/tags/*)
        tags[0]=${GITHUB_REF_NAME#v}
        tags[1]="$(echo "${GITHUB_REF_NAME#v}" | sed 's/\.[0-9][0-9]*$//')"
        tags[2]=latest
        push=yes
        ;;
    refs/heads/*)
        tags[0]=$GITHUB_REF_NAME
        push=no
        ;;
    *)
        exit 1;
esac

image=ghcr.io/cakemanny/kgrok-remote

case $(uname -m) in
    x86_64) suffix=amd64 ;;
    aarch64|arm64) suffix=arm64 ;;
    *) exit 1 ;;
esac

taglist=$(
  for tag in "${tags[@]}"; do
      echo -t "${image}:${tag}-${suffix}"
  done
)

# shellcheck disable=SC2086
docker build -f Dockerfile $taglist .

if [[ $push != "yes" ]]; then
    exit 0
fi

# shellcheck disable=SC2046
for tag in "${tags[@]}"; do
  docker push "${image}:${tag}-${suffix}"
done
