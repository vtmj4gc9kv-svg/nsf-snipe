#!/bin/bash
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/bin:$PATH"
if ! command -v gh >/dev/null 2>&1; then
  mkdir -p "$HOME/bin"
  curl -sL https://github.com/cli/cli/releases/download/v2.62.0/gh_2.62.0_linux_amd64.tar.gz | tar xz -C /tmp
  cp /tmp/gh_2.62.0_linux_amd64/bin/gh "$HOME/bin/gh"
fi
if ! python -c "import playwright" 2>/dev/null || [ ! -d "$HOME/.cache/ms-playwright" ]; then
  pip install playwright requests
  python -m playwright install --with-deps chromium
fi
if ! pgrep -f vinted_bot.py >/dev/null; then
  nohup python -u vinted_bot.py > bot.log 2>&1 &
fi
for i in $(seq 1 20); do
  sleep 3
  if gh codespace ports visibility 8765:public -c "$CODESPACE_NAME" > port.log 2>&1; then
    echo "Port 8765 ist jetzt public"; break
  fi
done
cat port.log
