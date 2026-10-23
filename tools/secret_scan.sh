#!/bin/sh
# Refuse to commit/push anything that looks like a credential. Run before every push:
#   sh tools/secret_scan.sh            (scans tracked + staged files)
# Install as a pre-commit hook:  ln -s ../../tools/secret_scan.sh .git/hooks/pre-commit
cd "$(git rev-parse --show-toplevel)" || exit 2
PATTERN='vsk_[A-Za-z0-9_-]{40,}|sk-ant-[A-Za-z0-9_-]{20,}|sk-(proj-)?[A-Za-z0-9]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[abp]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}'
FILES=$(git ls-files -c -o --exclude-standard)
[ -z "$FILES" ] && exit 0
# tests use obviously fake tokens built at runtime ("vsk_" + "A" * 43), never literals
HITS=$(echo "$FILES" | xargs /usr/bin/grep -I -n -E "$PATTERN" -- 2>/dev/null | /usr/bin/grep -v '^tools/secret_scan.sh:')
if [ -n "$HITS" ]; then
  echo "secret_scan: possible credential found, refusing:" >&2
  echo "$HITS" | cut -c1-120 >&2
  exit 1
fi
echo "secret_scan: clean ($(echo "$FILES" | wc -l) files)"
