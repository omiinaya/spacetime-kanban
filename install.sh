#!/usr/bin/env bash
# kanban install script — run from repo root after cloning
# Installs the kanban CLI to ~/.local/bin/kanban

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
KANBAN_SRC="${SCRIPT_DIR}/kanban"
KANBAN_DST="${BIN_DIR}/kanban"

if [ ! -f "$KANBAN_SRC" ]; then
  echo "❌ kanban CLI not found at ${KANBAN_SRC}"
  echo "   Run this script from the spacetimedb-kanban repo root."
  exit 1
fi

mkdir -p "$BIN_DIR"

cp "$KANBAN_SRC" "$KANBAN_DST"
chmod +x "$KANBAN_DST"

echo "✅ Installed kanban CLI to ${KANBAN_DST}"

# Check if BIN_DIR is on PATH
case ":${PATH:-}:" in
  *:"${BIN_DIR}":*) ;;
  *)
    echo "⚠ ${BIN_DIR} is not in your PATH."
    echo "  Add this to your ~/.bashrc:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

# Verify
echo ""
echo "Testing installation..."
if "${KANBAN_DST}" --help >/dev/null 2>&1; then
  echo "✅ kanban CLI installed and working."
  echo ""
  echo "Next steps:"
  echo "  1. Set your agent ID:  export KANBAN_AGENT_ID=claude-vscode"
  echo "  2. Verify connection:  kanban info"
  echo "  3. See available tasks: kanban list --status=available"
  echo "  4. For full setup guide: cat SETUP.md"
else
  echo "❌ Installation test failed."
  exit 1
fi
