#!/usr/bin/env bash
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
        ;;
    refs/heads/*)
        tags[0]=$GITHUB_REF_NAME
        ;;
    *)
        exit 1;
esac

image=ghcr.io/cakemanny/kgrok-remote

for tag in "${tags[@]}"; do
    docker builder imagetools create -t "${image}:${tag}" \
        "${image}:${tag}-amd64" \
        "${image}:${tag}-arm64"
done
