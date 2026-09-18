#!/bin/bash
# Pull the latest constitution and regenerate the HTML that /constitution/ includes.
# Requires git and pandoc.
set -e
cd "$(dirname "$0")"
git submodule update --init --remote constitution
pandoc constitution/constitution.md -o avery_website/templates/constitution-contents.html
