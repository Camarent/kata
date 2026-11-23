#!/bin/sh
# Enable the repo's privacy hooks (.githooks). The blocklist is a regex kept in your own git
# config, never in the repo:
#   git config --global --add privacy.blocklist 'your-private-address-or-name'
set -e
cd "$(dirname "$0")/../.."
git config core.hooksPath .githooks
echo "hooks enabled (core.hooksPath=.githooks)"
if [ -z "$(git config --get-all privacy.blocklist)" ]; then
  echo "note: privacy.blocklist is not set, so the hooks skip their check" >&2
fi
