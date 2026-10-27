#!/bin/sh
# Copyright 2026 Sean Whalen
# SPDX-License-Identifier: Apache-2.0
# Smoke test: build a fake disk image, run the collector in image mode under a
# given shell, and check the manifest and archive. Usage:
#   tests/smoke.sh [SHELL]     (SHELL defaults to sh; used for both the script
#                               and the find -exec workers via COLLECTOR_SH)
set -u
SHELL_UNDER_TEST=${1:-sh}
HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPT="$HERE/../collect-agent-artifacts.sh"
# macOS sets TMPDIR with a trailing slash and under the /var -> /private/var
# symlink; strip the slash and resolve the directory so the paths the checks
# build match the manifest's (#78).
_tmpdir=${TMPDIR:-/tmp}
WORK=$(mktemp -d "${_tmpdir%/}/cac-smoke.XXXXXX") && WORK=$(cd "$WORK" && pwd -P) || exit 1
ROOT="$WORK/root"
OUT="$WORK/out"
fail=0
ok()   { printf 'ok   %s\n' "$1"; }
bad()  { printf 'FAIL %s\n' "$1"; fail=1; }
check() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

# ---- fake image -----------------------------------------------------------
mkdir -p "$ROOT/etc" "$ROOT/home/alice/.claude/projects/-srv-proj" "$ROOT/home/alice/.claude/cache" \
  "$ROOT/home/alice/.gemini/antigravity-cli/conversations" "$ROOT/home/alice/.gemini/antigravity-cli/bin" \
  "$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/ms-python.python" \
  "$ROOT/Users/bob/Library/Application Support/Cursor/User/workspaceStorage/abc" \
  "$ROOT/Users/bob/.codex/sessions/2026/10/03" "$ROOT/srv/proj/.claude" "$ROOT/Users/bob/Documents/app" \
  "$ROOT/home/ollama/.ollama/models/blobs" "$ROOT/nonexistent" "$ROOT/home/dave"
cat >"$ROOT/etc/passwd" <<EOF
root:x:0:0:root:/root:/bin/sh
alice:x:1000:1000:Alice:/home/alice:/bin/bash
ollama:x:999:999::/home/ollama:/usr/sbin/nologin
nobody:x:65534:65534::/nonexistent:/usr/sbin/nologin
dave:x:1001:1001:Dave:/home/dave:/bin/sh
EOF
printf '{"type":"user","message":{"role":"user","content":"hi"},"timestamp":"2026-10-03T00:00:00Z"}\n' >"$ROOT/home/alice/.claude/projects/-srv-proj/s1.jsonl"
printf '{"display":"do things","timestamp":1759449600000,"project":"/srv/proj","sessionId":"s1"}\n' >"$ROOT/home/alice/.claude/history.jsonl"
printf '{"claudeAiOauth":{"accessToken":"sk-ant-oat-SECRET"}}\n' >"$ROOT/home/alice/.claude/.credentials.json"
printf '{"projects":{"/srv/proj":{}}}\n' >"$ROOT/home/alice/.claude.json"
printf 'cached junk\n' >"$ROOT/home/alice/.claude/cache/junk.bin"
printf 'weird "name" with spaces and a \\ backslash\n' >"$ROOT/home/alice/.claude/weird \"name\" with spaces \\ bs.txt"
printf 'token\n' >"$ROOT/home/alice/.gemini/antigravity-cli/antigravity-oauth-token"
printf 'db\n' >"$ROOT/home/alice/.gemini/antigravity-cli/conversations/c1.db"
head -c 300000 /dev/zero >"$ROOT/home/alice/.gemini/antigravity-cli/bin/webm_encoder"
ln -s log/cli-1.log "$ROOT/home/alice/.gemini/antigravity-cli/cli.log"
printf 'export FOO=1\n' >"$ROOT/home/alice/.bash_history"
printf 'settings\n' >"$ROOT/srv/proj/.claude/settings.local.json"
printf '# proj\n' >"$ROOT/srv/proj/CLAUDE.md"
head -c 2100000 /dev/zero >"$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/state.vscdb"
printf 'junk\n' >"$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/ms-python.python/x"
printf '{"folder":"file:///Users/bob/Documents/app"}\n' >"$ROOT/Users/bob/Library/Application Support/Cursor/User/workspaceStorage/abc/workspace.json"
printf 'rules\n' >"$ROOT/Users/bob/Documents/app/.cursorrules"
printf '{"cwd":"/Users/bob/Documents/app"}\n' >"$ROOT/Users/bob/.codex/sessions/2026/10/03/rollout-1.jsonl"
printf 'blob\n' >"$ROOT/home/ollama/.ollama/models/blobs/sha256-abc"
printf 'hist\n' >"$ROOT/home/ollama/.ollama/history"
# --- source-verified layouts for the per-platform catalog entries ---
mkdir -p "$ROOT/home/alice/.continue/sessions" "$ROOT/home/alice/.continue/index/lancedb" "$ROOT/srv/cont" \
  "$ROOT/home/alice/.local/share/crush" "$ROOT/srv/crushproj/.crush" "$ROOT/srv/gem" "$ROOT/home/alice/.gemini/tmp/gem" \
  "$ROOT/home/alice/.cline/data/settings" "$ROOT/home/alice/.cline/data/sessions/s1" "$ROOT/srv/clineproj" \
  "$ROOT/home/alice/.local/share/opencode" \
  "$ROOT/Users/bob/Library/Application Support/Claude/Cache" "$ROOT/Users/bob/Library/Application Support/Zed/extensions" \
  "$ROOT/Users/bob/Library/Application Support/Zed/threads" "$ROOT/Users/bob/.config/zed" \
  "$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/state" \
  "$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/checkpoints" "$ROOT/Users/bob/clineproj"
printf '[{"sessionId":"a","workspaceDirectory":"/srv/cont"}]\n' >"$ROOT/home/alice/.continue/sessions/sessions.json"
printf '{"mcpOauthStorage":{}}\n' >"$ROOT/home/alice/.continue/index/globalContext.json"
printf 'vec\n' >"$ROOT/home/alice/.continue/index/lancedb/data.lance"
printf '{}\n' >"$ROOT/srv/cont/.continuerc.json"
printf '{"projects":[{"path":"/srv/crushproj","data_dir":"/srv/crushproj/.crush"}]}\n' >"$ROOT/home/alice/.local/share/crush/projects.json"
printf 'sqlite\n' >"$ROOT/srv/crushproj/.crush/crush.db"
printf '{"projects":{"/srv/gem":"gem"}}\n' >"$ROOT/home/alice/.gemini/projects.json"
printf '/srv/gem\n' >"$ROOT/home/alice/.gemini/tmp/gem/.project_root"
printf '# gem\n' >"$ROOT/srv/gem/GEMINI.md"
printf '{"anthropic":{"apiKey":"sk-x"}}\n' >"$ROOT/home/alice/.cline/data/settings/providers.json"
printf '{"id":"s1","cwd":"/srv/clineproj","workspace_root":"/srv/clineproj"}\n' >"$ROOT/home/alice/.cline/data/sessions/s1/s1.json"
printf 'rules\n' >"$ROOT/srv/clineproj/.clinerules"
printf '{"openai":{"type":"api","key":"x"}}\n' >"$ROOT/home/alice/.local/share/opencode/auth.json"
printf 'TOKEN=1\n' >"$ROOT/home/alice/.env"
printf '{"oauth:tokenCache":"enc"}\n' >"$ROOT/Users/bob/Library/Application Support/Claude/config.json"
printf '{"mcpServers":{}}\n' >"$ROOT/Users/bob/Library/Application Support/Claude/claude_desktop_config.json"
printf 'cache\n' >"$ROOT/Users/bob/Library/Application Support/Claude/Cache/index"
printf 'ext\n' >"$ROOT/Users/bob/Library/Application Support/Zed/extensions/foo.wasm"
printf 'db\n' >"$ROOT/Users/bob/Library/Application Support/Zed/threads/threads.db"
printf '{"language_models":{}}\n' >"$ROOT/Users/bob/.config/zed/settings.json"
printf '[{"id":"t1","cwdOnTaskInitialization":"/Users/bob/clineproj"}]\n' >"$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/state/taskHistory.json"
printf 'ckpt\n' >"$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/checkpoints/x"
printf 'rules\n' >"$ROOT/Users/bob/clineproj/.clinerules"
# --- v1.3 catalog revision: exclusions that must not swallow evidence, new secrets, remote server dirs, discovery sources ---
mkdir -p "$ROOT/home/alice/.factory/cache/session-index" "$ROOT/home/alice/.factory/cache/sounds" "$ROOT/home/alice/.factory/sessions/-srv-droid" "$ROOT/srv/droid" \
  "$ROOT/home/alice/.kiro/powers/installed/p1" "$ROOT/home/alice/.kiro/sessions/cli" "$ROOT/srv/kiroproj" \
  "$ROOT/home/alice/.vscode-server/data/User/globalStorage/saoudrizwan.claude-dev/state" "$ROOT/srv/remoteproj" \
  "$ROOT/home/alice/.gemini/antigravity-ide/conversations" "$ROOT/home/alice/.gemini/config" "$ROOT/srv/agyproj" \
  "$ROOT/home/alice/.cursor/projects/-srv-proj" "$ROOT/home/alice/.copilot/pkg" "$ROOT/home/alice/.copilot/session-state/s1" "$ROOT/srv/copproj" \
  "$ROOT/home/alice/.claude/image-cache" "$ROOT/home/alice/.local/share/amp" "$ROOT/srv/ampproj/.amp" \
  "$ROOT/home/alice/.windsurf/transcripts" "$ROOT/srv/kiloproj/.kilo/worktrees/w1" "$ROOT/Users/bob/Library/Application Support/Ollama"
printf 'sqlite\n' >"$ROOT/home/alice/.factory/cache/session-index/index.db"
printf 'ding\n' >"$ROOT/home/alice/.factory/cache/sounds/done.wav"
printf '{"type":"session_start","cwd":"/srv/droid"}\n' >"$ROOT/home/alice/.factory/sessions/-srv-droid/s1.jsonl"
printf '# droid\n' >"$ROOT/srv/droid/AGENTS.md"
printf '{"mcpServers":{"x":{"env":{"TOKEN":"t"}}}}\n' >"$ROOT/home/alice/.kiro/powers/installed/p1/mcp.json"
printf '{"id":"k1","cwd":"/srv/kiroproj"}\n' >"$ROOT/home/alice/.kiro/sessions/cli/k1.json"
printf 'steer\n' >"$ROOT/srv/kiroproj/.kiroignore"
printf 'sqlite\n' >"$ROOT/home/alice/.vscode-server/data/User/globalStorage/state.vscdb"
printf '[{"id":"t2","cwdOnTaskInitialization":"/srv/remoteproj"}]\n' >"$ROOT/home/alice/.vscode-server/data/User/globalStorage/saoudrizwan.claude-dev/state/taskHistory.json"
printf 'rules\n' >"$ROOT/srv/remoteproj/.clinerules"
printf 'db\n' >"$ROOT/home/alice/.gemini/antigravity-ide/conversations/i1.db"
printf '{"mcpServers":{}}\n' >"$ROOT/home/alice/.gemini/config/mcp_config.json"
printf '{"display":"hi","timestamp":1759449600000,"workspace":"/srv/agyproj"}\n' >"$ROOT/home/alice/.gemini/antigravity-cli/history.jsonl"
printf 'ignore\n' >"$ROOT/srv/agyproj/.antigravityignore"
printf '{"accessToken":"x"}\n' >"$ROOT/home/alice/.cursor/auth.json"
printf '{"tok":"x"}\n' >"$ROOT/home/alice/.cursor/projects/-srv-proj/mcp-auth.json"
printf 'pkg\n' >"$ROOT/home/alice/.copilot/pkg/copilot"
printf '{"token":"x"}\n' >"$ROOT/home/alice/.copilot/config.json"
printf 'cwd: /srv/copproj\nbranch: main\n' >"$ROOT/home/alice/.copilot/session-state/s1/workspace.yaml"
printf '# cop\n' >"$ROOT/srv/copproj/AGENTS.md"
printf '{"k":"x"}\n' >"$ROOT/home/alice/.claude/.device-keys.json"
printf 'img\n' >"$ROOT/home/alice/.claude/image-cache/a.png"
printf '{"cwd":"/srv/ampproj","prompt":"hi"}\n' >"$ROOT/home/alice/.local/share/amp/history.jsonl"
printf 'amp\n' >"$ROOT/srv/ampproj/.amp/settings.json"
printf '{"step":1}\n' >"$ROOT/home/alice/.windsurf/transcripts/t1.jsonl"
printf 'wt\n' >"$ROOT/srv/kiloproj/.kilo/worktrees/w1/f"
printf '{"cwd":"/srv/kiloproj"}\n' >"$ROOT/home/alice/.cline/data/sessions/s1/s2.json"
printf 'db\n' >"$ROOT/Users/bob/Library/Application Support/Ollama/db.sqlite"

# --- 1.4.0 catalog round (2026-10-04): sixteen agents from the October 2026 backlog.
# One case per new exclusion, secret glob and attributed agent, as kind|agent|path
# relative to alice's home: excl is a directory and exclf a file that must be
# skipped_excluded, secret must be collected and flagged, agent must be collected
# under that agent. The same list is in smoke.ps1.
CASES14='
excl||.pearai/extensions
excl||.pearai/index/lancedb
excl||.pearai/types
excl||.pearai/out
excl||.pearai/node_modules
excl||.pearai/.diffs
excl||.pearai/.migrations
excl||.config/pearai/User/globalStorage/pearai.pearai-roo-cline/checkpoints
excl||.config/pearai/User/globalStorage/pearai.pearai-roo-cline/tasks/t1/checkpoints
excl||.config/pearai/User/globalStorage/pearai.pearai-roo-cline/cache
exclf||.pearai/index/codebase.sqlite
exclf||.pearai/dev_data/devdata.sqlite
secret||.pearai/config.json
secret||.pearai/config.ts
secret||.pearai/.env
secret||.pearai/.configs/c1/config.json
secret||.config/pearai/User/globalStorage/pearai.pearai-roo-cline/settings/pearai_agent_mcp_settings.json
agent|pearai|.config/pearai/User/globalStorage/state.vscdb
agent|pearai|.pearai/sessions/s1.json
exclf||.config/Code/User/globalStorage/sourcegraph.cody-ai/symf/symf-v0.0.16
exclf||.local/share/Cody-nodejs/symf/symf-v0.0.16
exclf||Library/Application Support/Cody-nodejs/Data/symf/symf-v0.0.16
excl||.local/share/Cody-nodejs/dist
excl||AppData/Roaming/Cody-nodejs/Config/dist
secret||.config/Cody-nodejs/user-settings.json
secret||AppData/Roaming/Cody-nodejs/Config/user-settings.json
secret||.config/gh/hosts.yml
secret||AppData/Roaming/GitHub CLI/hosts.yml
agent|cody|.config/Code/User/globalStorage/sourcegraph.cody-ai/symf/indexroot/meta.json
agent|cody|.vscode/cody.json
agent|cody|.local/share/Cody-nodejs/JetBrains-globalState/cody-local-chatHistory-v2
excl||.twinny/embeddings/ws/chunks.lance
excl||.twinny/server/plugins/p1/repos/r1/checkout
excl||.twinny/server/plugins/p1/repos/r1/index
secret||.config/Code/User/globalStorage/rjmacarthy.twinny/twinny-providers.json
secret||.twinny/node/identity.json
secret||.twinny/server/license
secret||.twinny/server/plugins/p1/settings.json
agent|twinny|.config/Code/User/globalStorage/rjmacarthy.twinny/twinny-providers.json
agent|twinny|.vscode-server/data/User/globalStorage/rjmacarthy.twinny/state.json
excl||.tabby/models
excl||.tabby/index
excl||.tabby/repositories
secret||.tabby/config.toml
secret||.tabby-client/agent/config.toml
agent|tabby|.tabby/ee/db.sqlite
agent|tabby|.tabby/ee/db.sqlite-wal
agent|tabby|.tabby/ee/db.sqlite-shm
agent|tabby|.config/JetBrains/IntelliJIdea2025.2/options/intellij-tabby.xml
excl||.openinterpreter/packages
excl||.openinterpreter/cache
excl||.openinterpreter/.tmp
excl||.openinterpreter/tmp
excl||.openinterpreter/plugins/cache
excl||.openinterpreter/skills/.system
excl||.openinterpreter/worktrees
excl||.openinterpreter/.sandbox
excl||.openinterpreter/.sandbox-bin
excl||.openinterpreter/visualizations
excl||.openinterpreter/models-cache
secret||.openinterpreter/auth.json
secret||.openinterpreter/.credentials.json
secret||.openinterpreter/credentials/c1
secret||.openinterpreter/device_id
secret||.openinterpreter/secrets/s1
secret||.openinterpreter/.sandbox-secrets/s1
secret||.openinterpreter/.env
secret||.openinterpreter/config.toml
secret||.codex/.env
agent|open-interpreter|.openinterpreter/history.jsonl
excl||.openhands/cache
excl||.openhands/agent-canvas/workspaces
excl||.openhands/agent-canvas/tmux
secret||.openhands/agent-canvas/secret-key.txt
secret||.openhands/agent-canvas/api-key.txt
secret||.openhands/settings.json
secret||.openhands/secrets.json
secret||.openhands/profiles/p1.json
secret||.openhands/provider-connections/c1.json
secret||.openhands/auth/a1.json
secret||.openhands/runtime-control/r1
secret||.openhands/agent_settings.json
secret||.openhands/cloud/c1.json
secret||.openhands/mcp.json
secret||.openhands/.jwt_secret
secret||.openhands/.keys
agent|openhands|.config/OpenHands Agent Canvas/config.json
agent|openhands|.openhands/conversations/c1/events/event-00000-e1.json
excl||.pi/agent/bin
excl||.pi/agent/tmp
excl||.pi/agent/npm/node_modules
excl||.pi/agent/git/g1/node_modules
excl||.pi/agent/git/g1/.git
excl||.pi/npm/node_modules
excl||.pi/git/g1/node_modules
excl||.pi/git/g1/.git
exclf||.pi/agent/tools/fd
exclf||.pi/agent/tools/rg.exe
exclf||.pi/server/s1.sock
secret||.pi/agent/auth.json
secret||.pi/agent/auth.json.bak
secret||.pi/agent/mcp-auth.json
secret||.pi/agent/oauth.json
secret||.pi/agent/models.json
secret||.pi/agent/mcp.json
secret||.pi/mcp.json
secret||.config/little-coder/models.json
agent|pi|.pi/agent/settings.json
agent|little-coder|.pi/agent/little-coder-prompt-history.json
agent|little-coder|.little-coder/state.json
agent|little-coder|.cache/little-coder/log.txt
excl||.letta/bin
excl||.letta/mod-cache
excl||.letta/tool_execution_dir
excl||.letta/chroma
excl||.memgpt/chroma
secret||.letta/settings.json
secret||.letta/pg_uri
secret||.letta/credentials
secret||.letta/lc-local-backend/providers/auth.json
secret||.letta/channels/telegram/accounts.json
secret||.letta/channels/whatsapp/auth/creds.json
secret||.letta/agents/a1/memory/.git/config
secret||.letta/agents/a1/memory/.git/letta-credential-helper.cmd
secret||.config/letta/settings.json
secret||.memgpt/credentials
agent|letta|.letta/transcripts/a1/c1/transcript.jsonl
excl||.hermes/hermes-agent/hermes_cli
excl||.hermes/hermes-agent/.git
excl||AppData/Local/hermes/hermes-agent/hermes_cli
excl||AppData/Local/hermes/hermes-agent/.venv
excl||.hermes/models
excl||.hermes/runtimes
excl||.hermes/node
excl||.hermes/installs
excl||.hermes/tools
excl||.hermes/sandboxes
excl||.hermes/checkpoints/store/objects
excl||.hermes/checkpoints/store/indexes
excl||.hermes/checkpoints/legacy-1
excl||.hermes/backups
excl||.hermes/browser-profile
excl||.hermes/browser-profiles
excl||.hermes/browser_profiles
excl||.hermes/chrome-debug
excl||.hermes/bot-desktop/browser-profile
excl||.hermes/plugins/p1/node_modules
excl||.hermes/plugins/p1/.venv
excl||AppData/Local/hermes/models
excl||AppData/Local/hermes/runtimes
excl||AppData/Local/hermes/node
excl||AppData/Local/hermes/installs
excl||AppData/Local/hermes/tools
excl||AppData/Local/hermes/sandboxes
excl||AppData/Local/hermes/checkpoints/store/objects
excl||AppData/Local/hermes/checkpoints/store/indexes
excl||AppData/Local/hermes/checkpoints/legacy-1
excl||AppData/Local/hermes/backups
excl||AppData/Local/hermes/browser-profile
excl||AppData/Local/hermes/browser-profiles
excl||AppData/Local/hermes/browser_profiles
excl||AppData/Local/hermes/chrome-debug
excl||AppData/Local/hermes/bot-desktop/browser-profile
excl||AppData/Local/hermes/plugins/p1/node_modules
excl||AppData/Local/hermes/plugins/p1/.venv
excl||.hermes/profiles/work/models
excl||.hermes_dev/models
excl||.config/Hermes/Cache
excl||.config/Hermes/Code Cache
excl||.config/Hermes/GPUCache
excl||Library/Application Support/Hermes/Cache
excl||Library/Application Support/Hermes/Code Cache
excl||Library/Application Support/Hermes/GPUCache
excl||AppData/Roaming/Hermes/Cache
excl||AppData/Roaming/Hermes/Code Cache
excl||AppData/Roaming/Hermes/GPUCache
secret||.hermes/.env
secret||.hermes/.env.bak1
secret||.hermes/.op.env
secret||.hermes/npmrc
secret||.hermes/auth.json
secret||.hermes/auth.json.1
secret||.hermes/auth/google_oauth.json
secret||.hermes/.anthropic_oauth.json
secret||.hermes/.copilot_jwt.json
secret||.hermes/google_token.json
secret||.hermes/google_chat_user_tokens/u1.json
secret||.hermes/slack_tokens.json
secret||.hermes/honcho.json
secret||.hermes/mem0.json
secret||.hermes/webhook_subscriptions.json
secret||.hermes/teams_pipeline_store.json
secret||.hermes/mcp-tokens/t1.json
secret||.hermes/vault/vault.key
secret||.hermes/browser_auth/state.json
secret||.hermes/pairing/p1.json
secret||.hermes/platforms/pairing/p1.json
secret||.hermes/whatsapp/session/creds.json
secret||.hermes/platforms/whatsapp/session/creds.json
secret||.hermes/matrix/store/s1
secret||.hermes/platforms/matrix/store/s1
secret||.hermes/cache/bws_cache1.json
secret||.hermes/weixin/accounts/a1.json
secret||.hermes/runtime/photon-sidecar.json
secret||.hermes/proxy/ca.key
secret||.hermes/home/.gitconfig
secret||AppData/Local/hermes/.env
secret||AppData/Local/hermes/.env.bak1
secret||AppData/Local/hermes/.op.env
secret||AppData/Local/hermes/npmrc
secret||AppData/Local/hermes/auth.json
secret||AppData/Local/hermes/auth.json.1
secret||AppData/Local/hermes/auth/google_oauth.json
secret||AppData/Local/hermes/.anthropic_oauth.json
secret||AppData/Local/hermes/.copilot_jwt.json
secret||AppData/Local/hermes/google_token.json
secret||AppData/Local/hermes/google_chat_user_tokens/u1.json
secret||AppData/Local/hermes/slack_tokens.json
secret||AppData/Local/hermes/honcho.json
secret||AppData/Local/hermes/mem0.json
secret||AppData/Local/hermes/webhook_subscriptions.json
secret||AppData/Local/hermes/teams_pipeline_store.json
secret||AppData/Local/hermes/mcp-tokens/t1.json
secret||AppData/Local/hermes/vault/vault.key
secret||AppData/Local/hermes/browser_auth/state.json
secret||AppData/Local/hermes/pairing/p1.json
secret||AppData/Local/hermes/platforms/pairing/p1.json
secret||AppData/Local/hermes/whatsapp/session/creds.json
secret||AppData/Local/hermes/platforms/whatsapp/session/creds.json
secret||AppData/Local/hermes/matrix/store/s1
secret||AppData/Local/hermes/platforms/matrix/store/s1
secret||AppData/Local/hermes/cache/bws_cache1.json
secret||AppData/Local/hermes/weixin/accounts/a1.json
secret||AppData/Local/hermes/runtime/photon-sidecar.json
secret||AppData/Local/hermes/proxy/ca.key
secret||AppData/Local/hermes/home/.gitconfig
secret||.hermes/profiles/work/.env
secret||.hermes_dev/auth.json
secret||.hermes/hermes-agent/.env
secret||AppData/Local/hermes/hermes-agent/.env
agent|hermes|.hermes/state.db
agent|hermes|.hermes/state.db-wal
agent|hermes|.hermes/state.db-shm
agent|hermes|.hermes/cache/terminal/out1.txt
agent|hermes|.hermes/hermes-agent/.env.example
agent|hermes|.hermes_dev/config.yaml
agent|hermes|AppData/Local/hermes/cache/terminal/out1.txt
agent|hermes|.config/Hermes/connection.json
excl||.openclaw/dev
excl||.openclaw/git
excl||.openclaw/npm
excl||.openclaw/npm-runtime
excl||.openclaw/tmp
excl||.openclaw/tools
excl||.openclaw/worktrees
excl||.openclaw/plugin-skills
excl||.openclaw/extensions/e1/node_modules
excl||.openclaw/sandbox/skills-workspaces
excl||.openclaw/agents/main/agent/tmp
excl||.openclaw/agents/main/agent/.tmp
excl||.openclaw/browser/b1/user-data/Default/Cache
excl||.openclaw/browser/b1/user-data/Default/Code Cache
excl||.openclaw/browser/b1/user-data/Default/GPUCache
excl||.openclaw/browser/b1/user-data/Default/Service Worker
excl||.openclaw-work/tools
excl||.clawdbot/tools
excl||.clawdbot/npm
secret||.openclaw/openclaw.json
secret||.openclaw/clawdbot.json.bak
secret||.openclaw-work/.env
secret||.openclaw/credentials/c1.json
secret||.openclaw/service-env/gateway.env
secret||.openclaw/agents/main/agent/auth-profiles.json
secret||.openclaw/agents/main/agent/models.json
secret||.openclaw/browser/b1/user-data/Default/Cookies
secret||.clawdbot/clawdbot.json
secret||.clawdbot/.env
secret||.clawdbot/credentials/c1
secret||.moltbot/moltbot.json
secret||.moltbot/.env
secret||.moltbot/credentials/c1
secret||.config/openclaw/gateway.env
agent|openclaw|.openclaw/agents/main/agent/openclaw-agent.sqlite
agent|openclaw|.openclaw/agents/main/agent/openclaw-agent.sqlite-wal
agent|openclaw|.openclaw-work/openclaw.json
agent|openclaw|.config/systemd/user/openclaw-gateway.service
agent|openclaw|Library/LaunchAgents/ai.openclaw.gateway.plist
excl||.nanobot/bin
excl||.nanobot/run
excl||.nanobot-work/cache
secret||.nanobot/config.json
secret||.nanobot/auth/a1
secret||.nanobot-work/whatsapp-auth/a1
secret||.nanobot/matrix-store/s1
agent|nanobot|.nanobot-work/sessions/0123456789abcdef0123456789abcdef/Y2xpOmRpcmVjdA.jsonl
agent|nanobot|Library/LaunchAgents/ai.nanobot.gateway.plist
excl||agent-zero/.venv
excl||Desktop/agent-zero/.conda
excl||agent-zero/main/.git
excl||agent-zero/main/tmp/playwright
excl||agent-zero/main/tmp/memory/embeddings
excl||agent-zero/main/usr/.time_travel
excl||agent-zero/main/usr/workdir/w1/.venv
excl||agent-zero/main/usr/workdir/w1/node_modules
excl||.local/share/a0/browser-profiles
excl||Library/Application Support/A0/Browser Profiles
excl||AppData/Local/A0/Browser Profiles
excl||.config/Agent Zero Launcher/Cache
excl||.config/Agent Zero Launcher/Code Cache
excl||.config/Agent Zero Launcher/GPUCache
excl||.config/Agent Zero Launcher/docker_manager/cache
secret||agent-zero/main/usr/.env
secret||agent-zero/main/usr/secrets.env
secret||Desktop/agent-zero/usr/settings.json
secret||agent-zero/main/usr/projects/p1/.a0proj/secrets.env
secret||agent-zero/.env
secret||agent-zero/main/tmp/secrets.env
secret||agent-zero/main/tmp/settings.json
secret||agent-zero/main/usr/plugins/_desktop/profiles/d1/.ssh/id_ed25519
secret||agent-zero/main/usr/plugins/_desktop/profiles/d1/.gnupg/k1
secret||.agent-zero/.env
secret||.agent-zero/session_cookies.json
secret||.config/Agent Zero Launcher/docker_manager/state.json
secret||.config/Agent Zero Launcher/Local State
agent|agent-zero|agent-zero/main/usr/chats/c1/chat.json
agent|agent-zero|Desktop/agent-zero/usr/chats/c1/chat.json
agent|agent-zero|.local/share/a0/config.json
secret||.config/shell_gpt/.sgptrc
agent|shellgpt|AppData/Local/Temp/chat_cache/mychat
agent|shellgpt|.config/shell_gpt/roles/default.json
excl||.local/share/local-deep-research/cache
excl||.local/share/local-deep-research/models
excl||.local/share/local-deep-research/journal_data
excl||.local/share/local-deep-research/library
excl||Library/Application Support/local-deep-research/cache
excl||Library/Application Support/local-deep-research/models
excl||Library/Application Support/local-deep-research/journal_data
excl||Library/Application Support/local-deep-research/library
excl||AppData/Local/local-deep-research/local-deep-research/cache
excl||AppData/Local/local-deep-research/local-deep-research/models
excl||AppData/Local/local-deep-research/local-deep-research/journal_data
excl||AppData/Local/local-deep-research/local-deep-research/library
excl||Documents/LocalDeepResearch/Library
secret||.local/share/local-deep-research/.secret_key
secret||Library/Application Support/local-deep-research/.secret_key
secret||AppData/Local/local-deep-research/local-deep-research/.secret_key
agent|local-deep-research|.local/share/local-deep-research/encrypted_databases/u1.db
agent|local-deep-research|Documents/LocalDeepResearch/report.md
'
H="$ROOT/home/alice"; B="$ROOT/Users/bob"
printf '%s\n' "$CASES14" | while IFS='|' read -r _k _a _r; do
  [ -n "$_r" ] || continue
  case "$_k" in
    excl) mkdir -p "$H/$_r"; printf 'x\n' >"$H/$_r/f" ;;
    *) mkdir -p "$H/$(dirname "$_r")"; printf 'x\n' >"$H/$_r" ;;
  esac
done
# discovery sources, one project each
mkdir -p "$H/.hermes/checkpoints/store/projects" "$ROOT/srv/hermesproj" "$H/.letta/lc-local-backend/conversations/c1" "$ROOT/srv/lettaproj/.letta" "$ROOT/srv/lettaproj2" \
  "$H/.pi/agent/sessions/--srv-piproj--" "$H/.pi/agent/experimental/sessions/s1" "$ROOT/srv/piproj/.pi" "$ROOT/srv/piproj2" "$ROOT/srv/pitrust" "$ROOT/srv/picrash" "$ROOT/srv/piexp" \
  "$H/.openinterpreter/sessions/2026/10/04" "$H/.openinterpreter/archived_sessions/2026/10/01" "$ROOT/srv/oiproj/.openinterpreter/rules" "$ROOT/srv/oiarch/.codewhale" \
  "$H/.openhands/agent-canvas/dev_conversations/a1" "$H/.openhands/agent-canvas/conversations/a2" "$H/.openhands/conversations/a3" \
  "$ROOT/srv/ohproj/.openhands" "$ROOT/srv/ohdev" "$ROOT/srv/ohcanvas" "$ROOT/srv/ohcli" "$H/.pearai/sessions" "$ROOT/srv/pearproj/.pearai-agent" \
  "$ROOT/srv/clawws" "$ROOT/srv/clawagent" "$ROOT/srv/clawlegacy" "$ROOT/srv/clawprofile" "$B/.openclaw" \
  "$H/.nanobot/sessions/0123456789abcdef0123456789abcdef" "$ROOT/srv/nanows" "$ROOT/srv/nanocfg/memory" "$ROOT/srv/tabbyproj" \
  "$H/.twinny/embeddings/twinproj" "$ROOT/srv/twinproj/src"
printf '{"workdir":"/srv/hermesproj","created_at":1759536000}\n' >"$H/.hermes/checkpoints/store/projects/0123456789abcdef.json"
printf '# hermes\n' >"$ROOT/srv/hermesproj/.hermes.md"
printf '{"type":"start","project":"/srv/lettaproj","agentId":"a1"}\n' >"$H/.letta/sessions.jsonl"
printf '{"hooks":{}}\n' >"$ROOT/srv/lettaproj/.letta/settings.json"
printf '{"type":"session","id":"c1","cwd":"/srv/lettaproj2"}\n' >"$H/.letta/lc-local-backend/conversations/c1/messages.jsonl"
printf '# letta\n' >"$ROOT/srv/lettaproj2/AGENTS.md"
printf '{"type":"session","version":3,"id":"u1","cwd":"/srv/piproj"}\n' >"$H/.pi/agent/sessions/--srv-piproj--/2026-10-04T00-00-00-000Z_u1.jsonl"
printf '{}\n' >"$ROOT/srv/piproj/.pi/settings.json"
printf '{"type":"session","version":1,"id":"u2","cwd":"/srv/piproj2"}\n' >"$H/.pi/agent/2026-10-01T00-00-00-000Z_u2.jsonl"
printf '# pi\n' >"$ROOT/srv/piproj2/AGENTS.md"
printf '{"/srv/pitrust":true}\n' >"$H/.pi/agent/trust.json"
printf '<html></html>\n' >"$ROOT/srv/pitrust/pi-session-2026-10-04.html"
printf '[{"cwd":"/srv/picrash","sessionFile":"x.jsonl"}]\n' >"$H/.pi/agent/crashes.json"
printf '# pi\n' >"$ROOT/srv/picrash/AGENTS.md"
printf '{"id":"s1","cwd":"/srv/piexp"}\n' >"$H/.pi/agent/experimental/sessions/s1/meta.json"
printf '# pi\n' >"$ROOT/srv/piexp/AGENTS.md"
printf '{"type":"session_meta","payload":{"cwd":"/srv/oiproj"}}\n' >"$H/.openinterpreter/sessions/2026/10/04/rollout-2026-10-04T00-00-00-u1.jsonl"
printf 'rule\n' >"$ROOT/srv/oiproj/.openinterpreter/rules/r.md"
printf '{"type":"session_meta","payload":{"cwd":"/srv/oiarch"}}\n' >"$H/.openinterpreter/archived_sessions/2026/10/01/rollout-2026-10-01T00-00-00-u2.jsonl"
printf 'notes\n' >"$ROOT/srv/oiarch/.codewhale/notes.md"
printf '{"workspaces":[{"id":"w1","path":"/srv/ohproj"}],"workspaceParents":[]}\n' >"$H/.openhands/workspaces.json"
printf 'echo setup\n' >"$ROOT/srv/ohproj/.openhands/setup.sh"
printf '{"workspace":{"working_dir":"/srv/ohdev"}}\n' >"$H/.openhands/agent-canvas/dev_conversations/a1/meta.json"
printf '{"workspace":{"working_dir":"/srv/ohcanvas"}}\n' >"$H/.openhands/agent-canvas/conversations/a2/meta.json"
printf '{"workspace":{"working_dir":"/srv/ohcli"}}\n' >"$H/.openhands/conversations/a3/base_state.json"
for _d in ohdev ohcanvas ohcli; do printf '# oh\n' >"$ROOT/srv/$_d/AGENTS.md"; done
printf '[{"sessionId":"s1","title":"t","workspaceDirectory":"/srv/pearproj"}]\n' >"$H/.pearai/sessions/sessions.json"
printf '{}\n' >"$ROOT/srv/pearproj/.pearairc.json"
printf '{"mcpServers":{}}\n' >"$ROOT/srv/pearproj/.pearai-agent/mcp.json"
printf "{\n  // JSON5\n  agents: {\n    defaults: { workspace: '/srv/clawws' },\n    entries: { main: { agentDir: \"/srv/clawagent\" } },\n  },\n}\n" >"$H/.openclaw/openclaw.json"
printf '{"agents":{"defaults":{"workspace":"/srv/clawlegacy"}}}\n' >"$H/.clawdbot/clawdbot.json"
printf '{agents:{defaults:{workspace:"/srv/clawprofile"}}}\n' >"$H/.openclaw-work/openclaw.json"
printf '# soul\n' >"$ROOT/srv/clawws/SOUL.md"
printf '# a\n' >"$ROOT/srv/clawagent/AGENTS.md"
printf '# id\n' >"$ROOT/srv/clawlegacy/IDENTITY.md"
printf '# mem\n' >"$ROOT/srv/clawprofile/MEMORY.md"
printf '{}\n' >"$B/.openclaw/openclaw.json"
ln -s .openclaw "$B/.clawdbot"
printf '/srv/nanows' >"$H/.nanobot/sessions/0123456789abcdef0123456789abcdef/.workspace"
printf '# hb\n' >"$ROOT/srv/nanows/HEARTBEAT.md"
printf '{"agents":{"defaults":{"workspace":"/srv/nanocfg"}}}\n' >"$H/.nanobot-work/config.json"
printf '# mem\n' >"$ROOT/srv/nanocfg/memory/MEMORY.md"
printf '[[repositories]]\nname = "p"\ngit_url = "file:///srv/tabbyproj"\n' >"$H/.tabby/config.toml"
printf '# tabby\n' >"$ROOT/srv/tabbyproj/AGENTS.md"
printf '{"files":{"/srv/twinproj/src/a.ts":{"hash":"h1"},"/srv/twinproj/b.ts":{"hash":"h2"}}}\n' >"$H/.twinny/embeddings/twinproj/manifest.json"
printf '# twin\n' >"$ROOT/srv/twinproj/AGENTS.md"

# --- 1.5.0 Docker volumes (2026-10-04): a root Docker volume matched to Agent
# Zero, an unmatched volume, and a rootless volume in alice's home.
DV="$ROOT/var/lib/docker/volumes"
mkdir -p "$DV/a0_usr/_data/chats/ctx1" "$DV/a0_usr/_data/tmp/playwright" "$DV/pgdata/_data" \
  "$H/.local/share/docker/volumes/tabby_data/_data/events"
printf '{"id":"ctx1","name":"chat","history":"[]"}\n' >"$DV/a0_usr/_data/chats/ctx1/chat.json"
printf 'API_KEY_OPENAI=sk-x\n' >"$DV/a0_usr/_data/.env"
printf 'junk\n' >"$DV/a0_usr/_data/tmp/playwright/junk"
printf 'pg\n' >"$DV/pgdata/_data/x"
printf '{"event":"completion"}\n' >"$H/.local/share/docker/volumes/tabby_data/_data/events/2026-10-01.json"
printf 'metadata\n' >"$DV/metadata.db"

# --- 2026-10-04 Muse Code: Meta's coding agent CLI. Cases in the CASES14 form,
# relative to alice's home; the same list is in smoke.ps1. The Windows binary is
# a file exclusion, the Linux launcher state is a dot-file glob inside
# ~/.local/bin, and two discovery sources point at projects.
CASES_MUSE='
excl||.local/share/muse/plugins/cache/builtin
excl||.local/share/muse/skills/bundled
excl||.local/share/muse/plugins/marketplaces
excl||.local/bin/.muse-update.Ab12Cd
excl||.muse/worktrees
exclf||AppData/Local/Programs/muse/muse-bin-1.4.2-R1.exe
exclf||AppData/Local/Programs/muse/.muse-update.4242.exe
secret||.config/muse/auth.json
secret||.config/muse/settings.json
agent|muse-code|.config/muse/trust.json
agent|muse-code|.local/share/muse/session-index.db
agent|muse-code|.local/share/muse/plugins/cache/local/p1/plugin.json
agent|muse-code|.local/bin/.muse-version
agent|muse-code|.local/bin/.muse-update-lock/pid
agent|muse-code|.muse/projects/slug/tracking.json
agent|muse-code|AppData/Local/Programs/muse/.muse-version
agent|muse-code|AppData/Local/Programs/muse/.muse-launcher.ps1
agent|muse-code|AppData/LocalLow/muse-shell-sandbox-01a0f000-0000-7000-8000-000000000001/tmp1.txt
'
printf '%s\n' "$CASES_MUSE" | while IFS='|' read -r _k _a _r; do
  [ -n "$_r" ] || continue
  case "$_k" in
    excl) mkdir -p "$H/$_r"; printf 'x\n' >"$H/$_r/f" ;;
    *) mkdir -p "$H/$(dirname "$_r")"; printf 'x\n' >"$H/$_r" ;;
  esac
done
printf 'x\n' >"$H/.local/bin/othertool"
MUSE_S="$H/.local/share/muse/sessions/2026/10/04/01a0f000-0000-7000-8000-000000000001"
mkdir -p "$MUSE_S" "$ROOT/srv/museproj/.muse/worktrees/w1" "$ROOT/srv/musetrust"
printf '{"schema_version":1,"projects":{"/srv/musetrust":{"decision":"trusted"}}}\n' >"$H/.config/muse/trust.json"
printf '{"schema_version":1,"stream":{"kind":"session","id":"01a0f000-0000-7000-8000-000000000001"},"payload_type":"runtime.session.metadata","payload":{"kind":"metadata","record":{"model_id":"m","workspace_root":"/srv/museproj"}}}\n' >"$MUSE_S/session.jsonl"
printf '{}\n' >"$ROOT/srv/museproj/.muse/hooks.json"
printf 'x\n' >"$ROOT/srv/museproj/.muse/worktrees/w1/f"
printf '# trusted\n' >"$ROOT/srv/musetrust/AGENTS.md"

# --- 2026-10-04 relocated Claude Code home: a config home moved with
# CLAUDE_CONFIG_DIR to ~/.claude-work, which keeps .claude.json inside it, and
# claude-code-router's ~/.claude-code-router, which the .claude-* catalog lines
# must not claim. The same files are in smoke.ps1.
CCW="$H/.claude-work"
CCW_S="$CCW/projects/-srv-ccwork/0a0b0c0d-0000-4000-8000-000000000001.jsonl"
mkdir -p "$CCW/projects/-srv-ccwork" "$H/.claude-code-router" "$ROOT/srv/ccwork/.claude" "$ROOT/srv/cchist/.claude"
printf '{"type":"user","cwd":"/srv/ccwork","message":{"role":"user","content":"hi"}}\n' >"$CCW_S"
printf '{"display":"hi","project":"/srv/cchist","timestamp":1790848800000}\n' >"$CCW/history.jsonl"
printf '{"projects":{"/srv/ccwork":{"allowedTools":[]}}}\n' >"$CCW/.claude.json"
printf '{"claudeAiOauth":{"accessToken":"sk-ant-oat-SECRET"}}\n' >"$CCW/.credentials.json"
# 2026-10-23 (#256): the session key, the daemon files and the .claude.json
# backup of a relocated home are collected by name and flagged secret.
CCW_K="$CCW/sessions/4343.0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef.key"
mkdir -p "$CCW/sessions" "$CCW/daemon" "$CCW/backups"
printf 'session key\n' >"$CCW_K"
printf '0123456789abcdef0123456789abcdef' >"$CCW/daemon/control.key"
printf '{"workers":{}}\n' >"$CCW/daemon/roster.json"
printf '{"oauthAccount":{}}\n' >"$CCW/backups/.claude.json.backup.1792800000000"
printf '{"PORT":3456}\n' >"$H/.claude-code-router/config.json"
printf '{}\n' >"$ROOT/srv/ccwork/.claude/settings.json"
printf '{}\n' >"$ROOT/srv/cchist/.claude/settings.json"

# 2026-10-04 bug round: #29. Catalog entries that differ only by case:
# .config/PearAI/User before .config/pearai/User, and .config/Cursor/User
# nested under .config/cursor. Distinct directories on a case-sensitive
# filesystem (Linux $TMPDIR); one directory each on a case-insensitive one
# (macOS), where the checks below expect one row per file. The same files
# are in smoke.ps1.
mkdir -p "$H/.config/PearAI/User" "$H/.config/pearai/User" "$H/.config/cursor" "$H/.config/Cursor/User"
printf '{}\n' >"$H/.config/PearAI/User/case29-upper.json"
printf '{}\n' >"$H/.config/pearai/User/case29-lower.json"
printf '{}\n' >"$H/.config/cursor/case29-cli.json"
printf '{}\n' >"$H/.config/Cursor/User/case29-editor.json"
CASE_INSENSITIVE=0
[ -e "$H/.config/pearai/User/case29-upper.json" ] && CASE_INSENSITIVE=1

# 2026-10-06 Ollama (#44): the model manifests under .ollama/models/manifests
# are collected while the blobs beside them stay excluded, and the systemd
# service account's home /usr/share/ollama, which none of the home globs
# reaches, is found through etc/passwd. The same files are in smoke.ps1,
# except the passwd home: the PowerShell collector does not read etc/passwd.
OLM="$ROOT/home/ollama/.ollama/models/manifests/registry.ollama.ai/library/llama3.2/latest"
mkdir -p "$(dirname "$OLM")" "$ROOT/usr/share/ollama/.ollama/models/blobs"
printf '{"schemaVersion":2}\n' >"$OLM"
TZ=UTC0 touch -t 202609140000.00 "$OLM"
printf 'svc-ollama:x:998:998::/usr/share/ollama:/usr/sbin/nologin\n' >>"$ROOT/etc/passwd"
printf 'hist\n' >"$ROOT/usr/share/ollama/.ollama/history"
printf 'blob\n' >"$ROOT/usr/share/ollama/.ollama/models/blobs/sha256-def"

# 2026-10-06 frameworks sweep (#64): agent frameworks, studios and self-hosted
# platforms. Cases in the CASES14 form, relative to alice's home; the same list
# is in smoke.ps1. CrewAI names its run directory after the project folder, so
# its Linux and macOS lines are file-anchored below a mid-path wildcard
# (.local/share/myproj); the Windows line is the class AppData/Local/[Cc]rew[Aa][Ii],
# tested with CrewAI in alice's home and crewai in bob's. Apache Camel JBang
# shares ~/.camel with CAMEL, so a JBang status file there must not be collected.
CASES_FW='
agent|autogen-studio|.autogenstudio/autogen04203.db
secret||.autogenstudio/.env
secret||.autogenstudio/temp_env_vars.env
secret||.config/crewai/settings.json
secret||.local/share/crewai/credentials/tokens.enc
secret||.local/share/crewai/credentials/secret.key
secret||Library/Application Support/crewai/credentials/tokens.enc
secret||AppData/Local/CrewAI/credentials/secret.key
agent|crewai|.crewai/model_catalog_cache.json
agent|crewai|.local/share/myproj/latest_kickoff_task_outputs.db
agent|crewai|.local/share/myproj/latest_kickoff_task_outputs.db-wal
agent|crewai|.local/share/myproj/flow_states.db
agent|crewai|.local/share/myproj/.crewai_user.json
agent|crewai|Library/Application Support/myproj/latest_kickoff_task_outputs.db
agent|crewai|AppData/Local/CrewAI/myproj/latest_kickoff_task_outputs.db
secret||.camel/gmail_token.json
agent|camel-ai|.camel/gmail_token.json
agent|camel-ai|.camel/skills/s1/SKILL.md
agent|camel-ai|.config/camel/skills/s2/SKILL.md
secret||.config/difyctl/tokens.yml
secret||AppData/Roaming/difyctl/tokens.yml
secret||AppData/Local/difyctl/tokens.yml
agent|dify|.config/difyctl/config.yml
excl||.flowise/vectorstore
secret||.flowise/encryption.key
secret||.flowise/jwt_auth_token_secret.key
agent|flowise|.flowise/database.sqlite
excl||.langflow/knowledge_bases
excl||AppData/Roaming/com.LangflowDesktop/knowledge_bases
excl||Library/Application Support/com.LangflowDesktop/venv
excl||Library/Application Support/com.LangflowDesktop/python_env
excl||AppData/Local/com.LangflowDesktop/venv
excl||AppData/Local/com.LangflowDesktop/python_env
excl||AppData/Local/com.LangflowDesktop/cache
excl||.cache/langflow/profile_pictures
excl||Library/Caches/langflow/profile_pictures
excl||AppData/Local/langflow/langflow/Cache/profile_pictures
secret||.cache/langflow/secret_key
secret||.cache/langflow/cache_secret_key
secret||Library/Caches/langflow/secret_key
secret||AppData/Local/langflow/langflow/Cache/secret_key
secret||.langflow/data/.env
secret||AppData/Roaming/com.LangflowDesktop/data/.env
agent|langflow|.langflow/data/database.db
agent|langflow|Library/Logs/com.LangflowDesktop/langflow.log
secret||.metagpt/config2.yaml
secret||.metagpt/config2.bak
excl||.n8n/nodes/node_modules
excl||.n8n/custom/node_modules
excl||.n8n/node-definitions
excl||.n8n/n8n-sdk-templates
secret||.n8n/config
secret||.n8n/ssh/key
agent|n8n|.n8n/database.sqlite
agent|n8n|.n8n-local-gateway/log
agent|n8n|.n8n-gateway/settings.json
secret||.config/pydantic-clai2/credentials-default.enc
secret||.config/pydantic-clai2/logfire/logfire_credentials.json
agent|pydantic-clai|.config/pydantic-clai2/sessions.db
agent|pydantic-clai|.pydantic-ai/prompt-history.txt
excl||.config/open-interpreter/models
excl||Library/Application Support/open-interpreter/models
excl||AppData/Local/open-interpreter/open-interpreter/models
secret||.config/open-interpreter/profiles/default.yaml
secret||Library/Application Support/open-interpreter/profiles/default.yaml
secret||AppData/Local/open-interpreter/open-interpreter/profiles/default.yaml
secret||.config/Open Interpreter/config.yaml
secret||Library/Application Support/Open Interpreter Terminal/config.yaml
secret||AppData/Local/Open Interpreter/Open Interpreter/config.yaml
agent|open-interpreter|.config/open-interpreter/conversations/hello__October_06_2026_10-00-00.json
agent|open-interpreter|.config/Open Interpreter Terminal/conversations/old.json
agent|open-interpreter|.cache/open-interpreter/telemetry_user_id
'
printf '%s\n' "$CASES_FW" | while IFS='|' read -r _k _a _r; do
  [ -n "$_r" ] || continue
  case "$_k" in
    excl) mkdir -p "$H/$_r"; printf 'x\n' >"$H/$_r/f" ;;
    *) mkdir -p "$H/$(dirname "$_r")"; printf 'x\n' >"$H/$_r" ;;
  esac
done
printf '{}\n' >"$H/.camel/4242-status.json"
printf 'x\n' >"$H/.local/share/myproj/unrelated.txt"
mkdir -p "$B/AppData/Local/crewai/myproj" "$B/AppData/Local/crewai/credentials"
printf 'x\n' >"$B/AppData/Local/crewai/myproj/latest_kickoff_task_outputs.db"
printf 'x\n' >"$B/AppData/Local/crewai/credentials/tokens.enc"

# 2026-10-11 Claude Desktop Linux deb and Claude Code 2.1.295 session keys (#73, #76)
# The layout observed under ~/.config/Claude from the Linux .deb: logs inside
# the data directory, the space-link signing key under
# spaces-present/<acct 8 hex>/<org 8 hex>/, the CLI temp-root list in
# git-shadow/, a Code-tab record, and the downloaded CLI under claude-code/,
# which stays excluded. Beside them, Claude Code's per-process session key
# next to its sessions/<pid>.json. Checks follow the default and --no-secrets
# runs below; the same files are in smoke.ps1.
C76="$H/.config/Claude"; O76="0a0a0a0a-0000-4000-8000-00000000000a/0b0b0b0b-0000-4000-8000-00000000000b"
X76=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
K76="$H/.claude/sessions/4242.$X76.key"
mkdir -p "$C76/spaces-present/0a0a0a0a/0b0b0b0b" "$C76/git-shadow" "$C76/logs" "$C76/claude-code/2.1.295/9b32b47ec4b3" \
  "$C76/claude-code-sessions/$O76" "$H/.claude/sessions"
printf 'link-key ciphertext\n' >"$C76/spaces-present/0a0a0a0a/0b0b0b0b/link-key"
printf '["/tmp/claude-1000"]\n' >"$C76/git-shadow/cli-temp-roots.json"
printf '2026-10-11 10:00:00 [info] [CCD] Installed\n' >"$C76/logs/main.log"
printf 'ELF\n' >"$C76/claude-code/2.1.295/9b32b47ec4b3/claude"
printf '{"sha256":"%s","size":4}\n' "$X76" >"$C76/claude-code/2.1.295/9b32b47ec4b3/.payload"
printf '%s' "$X76" >"$C76/claude-code/2.1.295/9b32b47ec4b3/.verified"
printf '{"sessionId":"local_76767676-7676-4676-8676-767676767676","cliSessionId":"76767676-0000-4000-8000-000000000076","cwd":"/srv/proj","originCwd":"/srv/proj"}\n' >"$C76/claude-code-sessions/$O76/local_76767676-7676-4676-8676-767676767676.json"
printf '{"pid":4242,"sessionId":"76767676-0000-4000-8000-000000000076","entrypoint":"claude-desktop","kind":"interactive"}\n' >"$H/.claude/sessions/4242.json"
printf 'session key\n' >"$K76"

# 2026-10-11 Claude Code CLI cache directory (#81)
# The CLI's env-paths cache directory, observed on macOS under
# ~/Library/Caches/claude-cli-nodejs: per-project MCP server logs,
# <cwd slug>/mcp-logs-<server>/<timestamp>.jsonl, one {cwd, debug,
# sessionId, timestamp} object per line. Collected as claude-code, not
# secret. Checks follow the default run below; the same file is in smoke.ps1.
F81="$H/Library/Caches/claude-cli-nodejs/-home-alice-proj/mcp-logs-terminal/2026-10-12T02-23-51-709Z.jsonl"
mkdir -p "$(dirname "$F81")"
printf '%s\n' '{"cwd":"/home/alice/proj","debug":"MCP server \"terminal\": connected","sessionId":"81818181-0000-4000-8000-000000000081","timestamp":"2026-10-12T02:23:51.709Z"}' >"$F81"
# The Windows layout puts the slug directories under Cache/, which the
# catalog names as Cache/* so the PowerShell exclusion */Claude*/Cache,
# matched without case, does not prune it.
W81="$H/AppData/Local/claude-cli-nodejs/Cache/C--Users-alice-proj/mcp-logs-ccd-host/2026-10-12T02-23-51-709Z.jsonl"
mkdir -p "$(dirname "$W81")"
printf '%s\n' '{"cwd":"C:\\Users\\alice\\proj","debug":"MCP server \"ccd-host\": connected","sessionId":"81818181-0000-4000-8000-000000000081","timestamp":"2026-10-12T02:23:51.709Z"}' >"$W81"

# 2026-10-13 Antigravity desktop app (#83, #84)
# The layout observed on macOS from the desktop app 2.23.0: its data
# directory ~/.gemini/antigravity with a conversation database, a crash log,
# a plugin's OAuth token and binary under plugin_data/, the binaries in bin/,
# and the plugin marketplace cache beside a cache file the app shares with
# the CLI; then the Electron user-data directory with its Cache and Code
# Cache, the macOS logs directory, and the Windows form of the user-data
# directory. Cache under the Electron directory is excluded by its three
# explicit bases, never by */Antigravity/Cache, which the PowerShell match
# would also apply to .gemini/antigravity/cache. Checks follow the default
# and --no-secrets runs below; the same files are in smoke.ps1.
G83="$H/.gemini/antigravity"; E83="$H/Library/Application Support/Antigravity"; W83="$H/AppData/Roaming/Antigravity"
mkdir -p "$G83/conversations" "$G83/crashes" "$G83/plugin_data/gdocs/bin" "$G83/bin" "$G83/cache/marketplaces/official" \
  "$E83/Cache" "$E83/Code Cache/js" "$H/Library/Logs/Antigravity" "$W83/Cache"
printf 'sqlite\n' >"$G83/conversations/a1.db"
printf 'crash\n' >"$G83/crashes/crash_1.log"
printf '{"token":{"access_token":"x","refresh_token":"y"}}\n' >"$G83/plugin_data/gdocs/token.json"
printf 'bin\n' >"$G83/plugin_data/gdocs/bin/gdocs-1"
printf 'bin\n' >"$G83/bin/webm_encoder"
printf '{"name":"official","plugins":[]}\n' >"$G83/cache/marketplaces/official/marketplace.json"
printf '{"x":"a1"}\n' >"$G83/cache/last_conversations.json"
printf '{"lastCreatedProjectId":"p1"}\n' >"$E83/app_storage.json"
printf 'cache\n' >"$E83/Cache/data_0"
printf 'js\n' >"$E83/Code Cache/js/x"
printf '[2026-10-13 18:28:00.000] [info]  Starting app (v2.23.0)\n' >"$H/Library/Logs/Antigravity/main.log"
printf '{"lastCreatedProjectId":"p1"}\n' >"$W83/app_storage.json"
printf 'cache\n' >"$W83/Cache/data_0"

# 2026-10-13 Antigravity Linux round (#83, #90, #91)
# From the Ubuntu install of CLI 1.3.4 and the desktop app 2.23.1: the CLI's
# file secret store plugin-secrets.json under the lower-case
# ~/.config/antigravity (secret), the spell-check Dictionaries directory of
# the Electron user-data directory and the sidecar SDK the app installs
# twice, under .gemini/antigravity/lib/node_modules and
# .gemini/config/node_modules (excluded), and two app project files: one
# pretty-printed exactly as observed, with two spaces between the colon and
# the file:/// folderUri, and one with a percent-encoded Windows drive
# letter. Both projects must be discovered (#91). The Dictionaries fixture
# sits in the macOS user-data directory: alice's .config/Antigravity would
# be the same directory as .config/antigravity on a case-insensitive
# filesystem. Checks follow the default and --no-secrets runs below; the
# same files, in the Windows layout, are in smoke.ps1.
mkdir -p "$H/.config/antigravity" "$E83/Dictionaries" "$G83/lib/node_modules/sidecar_sdk" \
  "$H/.gemini/config/node_modules/sidecar_sdk" "$H/.gemini/config/projects" "$ROOT/srv/agyapp" "$ROOT/srv/agywin"
printf '{"gdocs":"x"}\n' >"$H/.config/antigravity/plugin-secrets.json"
printf 'bdic\n' >"$E83/Dictionaries/en-US-10-1.bdic"
printf 'export {}\n' >"$G83/lib/node_modules/sidecar_sdk/index.mjs"
printf 'export {}\n' >"$H/.gemini/config/node_modules/sidecar_sdk/index.mjs"
printf '{\n  "id": "91919191-0000-4000-8000-000000000091",\n  "projectResources": {\n    "resources": [\n      {\n        "folderUri":  "file:///srv/agyapp"\n      }\n    ]\n  }\n}\n' >"$H/.gemini/config/projects/91919191-0000-4000-8000-000000000091.json"
printf '{\n  "id": "91919191-0000-4000-8000-000000000092",\n  "projectResources": {\n    "resources": [\n      {\n        "folderUri":  "file:///c%%3A/srv/agywin"\n      }\n    ]\n  }\n}\n' >"$H/.gemini/config/projects/91919191-0000-4000-8000-000000000092.json"
printf 'ignore\n' >"$ROOT/srv/agyapp/.antigravityignore"
printf 'ignore\n' >"$ROOT/srv/agywin/.antigravityignore"

# 2026-10-14 home patterns and the working directory (#105)
# A directory outside the image with home and Users subdirectories, the
# working directory of the cwd105 run below: the home patterns must be
# expanded under the image root, not here, so bob (no passwd entry, found
# only by the Users/* pattern) is still collected. The same in smoke.ps1.
CWD105="$WORK/cwd105"
mkdir -p "$CWD105/home/analyst" "$CWD105/Users/analyst"

# 2026-10-14 catalog match that is an excluded file (#107)
# Muse Code's staged updater as a file, matched by the catalog line
# .local/bin/.muse-* and by the exclusion .local/bin/.muse-update.*: one
# skipped_excluded row with its size, as for a file a walk prunes; collected
# with --full; counted by the inventory only with --full. The same file is
# in smoke.ps1.
printf '1070\n' >"$H/.local/bin/.muse-update.107.exe"

# 2026-10-14 output directory under a file (#108)
# A plain file outside the image: the check after the read-only output
# directory check below gives -o a path under it. The same in smoke.ps1.
FILE108="$WORK/file108"
printf 'x\n' >"$FILE108"

# 2026-10-14 exclusion globs and the working directory (#109)
# A plugin node_modules in alice's home, excluded by the wildcard glob
# .claude/plugins/*/node_modules, and a directory outside the image holding
# another tree that the glob matches, the working directory of the cwd109
# run below: the glob must reach find unexpanded. The same in smoke.ps1.
mkdir -p "$H/.claude/plugins/y/node_modules" "$WORK/cwd109/.claude/plugins/x/node_modules"
printf 'module.exports = 1\n' >"$H/.claude/plugins/y/node_modules/f.js"

# 2026-10-14 CDPATH in the environment (#110), sh only: PowerShell has no
# CDPATH. A directory for CDPATH that holds a decoy root, named like the
# image root, for the cdpath110 run below.
mkdir -p "$WORK/cdp110/root/home"

# 2026-10-14 Antigravity on Windows (#83)
# From the Windows 11 install of the desktop app 2.23.1 and CLI 1.3.5: the
# marketplace staging directory under AppData/Local/antigravity (the Windows
# form of .cache/antigravity, empty on the install, given a file here so
# it has a row), beside the installer's AppData/Local/antigravity-updater
# and the app's program directory AppData/Local/Programs/antigravity, which
# the catalog line must not match. Checks follow the default run below; the
# same files are in smoke.ps1.
L83="$H/AppData/Local"
mkdir -p "$L83/antigravity/staging" "$L83/antigravity-updater" "$L83/Programs/antigravity"
printf 'staged\n' >"$L83/antigravity/staging/s1"
printf 'exe\n' >"$L83/antigravity-updater/installer.exe"
printf 'exe\n' >"$L83/Programs/antigravity/Antigravity.exe"

# 2026-10-15 ChatGPT desktop as the OpenAI.Codex package (#113)
# From the Windows 11 install of ChatGPT 26.1007.9446.0: the Chromium
# profile under the package's web/Codex user-data directory, with a
# storage partition, the app log and the MSIX settings hive. The component
# cache beside the profile is not a catalog line and must get no row. The
# bundled Codex's copied binaries and global state go in bob's .codex
# (#115, #116). Checks follow the default and --no-secrets runs below; the
# same files are in smoke.ps1 under alice.
P113="$H/AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0"
C113="$P113/LocalCache/Roaming/Codex/web/Codex"
X113="$C113/Default/Partitions/codex-browser-app"
mkdir -p "$C113/Default/Local Storage/leveldb" "$C113/Default/Network" "$C113/Default/Cache" \
  "$X113/Network" "$X113/Cache" "$C113/component_crx_cache" \
  "$P113/LocalCache/Local/Codex/Logs/2026/10/15" "$P113/Settings" \
  "$B/.codex/plugins/.plugin-appserver"
printf 'ldb\n' >"$C113/Default/Local Storage/leveldb/000003.log"
printf '{"os_crypt":{}}\n' >"$C113/Local State"
printf 'cookies\n' >"$C113/Default/Network/Cookies"
printf 'cookies\n' >"$X113/Network/Cookies"
printf 'logins\n' >"$C113/Default/Login Data"
printf 'cache\n' >"$C113/Default/Cache/data_0"
printf 'cache\n' >"$X113/Cache/data_0"
printf '{}\n' >"$C113/component_crx_cache/metadata.json"
printf 'log\n' >"$P113/LocalCache/Local/Codex/Logs/2026/10/15/codex-desktop-x.log"
printf 'hive\n' >"$P113/Settings/settings.dat"
printf 'exe\n' >"$B/.codex/plugins/.plugin-appserver/codex.exe"
printf '{}\n' >"$B/.codex/.codex-global-state.json"

# 2026-10-15 ChatGPT desktop on macOS (#121)
# From the macOS 26.6.2 install of ChatGPT 26.1007.71326 (bundle id
# com.openai.codex): the Chromium profile under Application Support/Codex
# (its cookie store directly in the profile), the bundled MCP server's
# script beside its manifest, the app log, preferences, URL-session
# cookies and the computer-use group container, and the computer-use app
# bundle the app copies into .codex. The component cache beside the
# profile gets no row. Checks follow the default run below; the same
# files are in smoke.ps1 under alice.
M121="$B/Library/Application Support/Codex"
X121="$M121/Default/Partitions/codex-browser-app"
G121="$B/Library/Group Containers/2DC432GLL2.com.openai.sky.CUAService"
U121="$B/.codex/computer-use"
mkdir -p "$M121/Default/Local Storage/leveldb" "$M121/Default/Cache" "$X121/Cache" \
  "$M121/executor-plugins/codex-app-tools" "$M121/component_crx_cache" \
  "$B/Library/Logs/com.openai.codex/2026/10/15" "$B/Library/Preferences" \
  "$B/Library/HTTPStorages" "$G121/IPC" "$U121/Codex Computer Use.app/Contents"
printf 'ldb\n' >"$M121/Default/Local Storage/leveldb/000003.log"
printf 'cookies\n' >"$M121/Default/Cookies"
printf 'cookies\n' >"$X121/Cookies"
printf 'logins\n' >"$M121/Default/Login Data"
printf 'cache\n' >"$M121/Default/Cache/data_0"
printf 'cache\n' >"$X121/Cache/data_0"
printf 'js\n' >"$M121/executor-plugins/codex-app-tools/server.mjs"
printf '{}\n' >"$M121/executor-plugins/codex-app-tools/.mcp.json"
printf '{}\n' >"$M121/component_crx_cache/metadata.json"
printf 'log\n' >"$B/Library/Logs/com.openai.codex/2026/10/15/codex-desktop-x.log"
printf 'plist\n' >"$B/Library/Preferences/com.openai.codex.plist"
printf 'cookies\n' >"$B/Library/HTTPStorages/com.openai.codex.binarycookies"
: >"$G121/IPC/computeruse.sock.lock"
printf 'plist\n' >"$U121/Codex Computer Use.app/Contents/Info.plist"
printf '{}\n' >"$U121/config.json"

# 2026-10-15 special files (#120)
# Codex CLI 0.162.1 keeps Unix domain sockets under .codex
# (app-server-daemon/daemon-updater.sock, ipc/ipc.sock). A socket and a FIFO
# each get one skipped_special row naming their kind and are never opened.
# The FIFO is sh only: PowerShell cannot create one. The socket is bound with
# python3 from inside its directory, since a full path under a long TMPDIR
# can pass the 104-byte (macOS) or 108-byte (Linux) socket path limit; when
# python3 is absent or the bind fails, the socket checks are skipped. Checks
# follow the default run below; the socket is in smoke.ps1 under alice.
S120="$ROOT/home/alice/.codex"
mkdir -p "$S120/ipc" "$S120/app-server-daemon"
mkfifo "$S120/ipc/ipc.fifo"
SOCK120=0
if command -v python3 >/dev/null 2>&1 && python3 -c 'import os,socket,sys
os.chdir(os.path.dirname(sys.argv[1]))
socket.socket(socket.AF_UNIX).bind(os.path.basename(sys.argv[1]))' \
  "$S120/app-server-daemon/daemon-updater.sock" 2>/dev/null &&
  [ -S "$S120/app-server-daemon/daemon-updater.sock" ]; then
  SOCK120=1
else
  printf 'note: no Unix domain socket could be created; socket checks skipped\n'
fi

# 2026-10-16 GitHub Copilot Desktop (#147)
# From the Ubuntu 26.04 arm64 install of GitHub Copilot Desktop 1.1.29: the
# app shares .copilot with the CLI. Its store, run files, chat and repository
# directories and log are nested copilot-desktop entries; its sessions stay
# copilot-cli. A session cwd under .copilot (a chat directory, a worktree) is
# not a project. The data directory and Foundry Local's directory are its own
# entries. A clone's .git is collected (its checkpoint refs), less objects and
# index; the clones' working trees and the worktrees stay excluded with repos.
# entries. Checks follow the default and --no-secrets runs below; the same
# files are in smoke.ps1 under alice.
D147="$ROOT/home/alice/.copilot"
L147="$ROOT/home/alice/.local/share/com.github.githubapp"
mkdir -p "$D147/run" "$D147/chats/2026-10-16/x-5d404e14" "$D147/repos/proj" \
  "$D147/repos/copilot-worktrees/proj/alice-x" "$D147/logs" "$D147/session-state/s2" \
  "$D147/session-state/s3" "$L147/localstorage" "$L147/app-skills/af" \
  "$ROOT/home/alice/.github-copilot-cli/logs"
printf 'sqlite\n' >"$D147/data.db"
printf 'wal\n' >"$D147/data.db-wal"
printf '%s\n' 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA' >"$D147/run/ws.token"
printf '12345\n' >"$D147/run/ws.port"
: >"$D147/chats/2026-10-16/x-5d404e14/.keep"
printf '# proj\n' >"$D147/repos/proj/README.md"
R147="$D147/repos/proj/.git"
C147="$R147/refs/copilot/checkpoints/5e55a0a1-0000-4000-8000-000000000001/00000000000000000001"
mkdir -p "$C147" "$R147/objects/ab"
printf 'ref: refs/heads/main\n' >"$R147/HEAD"
printf '0123456789abcdef0123456789abcdef01234567\n' \
  >"$C147/e0000000-0000-4000-8000-000000000020"
printf 'object\n' >"$R147/objects/ab/cdef0123"
printf 'index\n' >"$R147/index"
printf '# wt\n' >"$D147/repos/copilot-worktrees/proj/alice-x/AGENTS.md"
printf 'log\n' >"$D147/logs/github-app.1.log"
printf 'cwd: /home/alice/.copilot/chats/2026-10-16/x-5d404e14\nclient_name: github/autopilot\n' \
  >"$D147/session-state/s2/workspace.yaml"
printf 'cwd: /home/alice/.copilot/repos/copilot-worktrees/proj/alice-x\nclient_name: github/autopilot\n' \
  >"$D147/session-state/s3/workspace.yaml"
printf 'sqlite\n' >"$L147/localstorage/tauri_localhost_0.localstorage"
printf '# af\n' >"$L147/app-skills/af/SKILL.md"
printf 'log\n' >"$ROOT/home/alice/.github-copilot-cli/logs/foundry.core20261016.log"

# 2026-10-17 Copilot Desktop Windows round (#147)
# From the Windows 11 arm64 install of GitHub Copilot Desktop 1.1.30: the
# WebView2 user data folder (AppData/Local/com.github.githubapp) is a
# copilot-desktop entry less its Chromium caches; a project the agent built in
# a chat directory keeps its files but not its node_modules; the Copilot CLI's
# marketplace clone is excluded (#131). A session directory with no
# events.jsonl is a pool or probe session the app never prompted, and its cwd
# (the install directory on Windows) is not a project; s1, s2 and s3 get an
# events.jsonl so the discovery and .copilot rules above stay tested. Checks
# follow the default run below; the same files are in smoke.ps1 under alice.
W147="$ROOT/home/alice/AppData/Local/com.github.githubapp/EBWebView"
P147="$D147/chats/2026-10-17/x-90825c78/proj"
K147="$ROOT/home/alice/AppData/Local/copilot/marketplaces"
mkdir -p "$W147/Default/Local Storage/leveldb" "$W147/Default/Cache/Cache_Data" "$W147/Default/Network" \
  "$W147/component_crx_cache" "$P147/node_modules/m" "$K147/m/.git" \
  "$D147/session-state/s4" "$ROOT/srv/coppool"
printf 'leveldb\n' >"$W147/Default/Local Storage/leveldb/000003.log"
printf 'cookies\n' >"$W147/Default/Network/Cookies"
printf '{"os_crypt":{}}\n' >"$W147/Local State"
printf 'cache\n' >"$W147/Default/Cache/Cache_Data/x"
printf 'crx\n' >"$W147/component_crx_cache/x"
printf '{"name":"proj"}\n' >"$P147/package.json"
printf 'module\n' >"$P147/node_modules/m/index.js"
printf 'ref: refs/heads/main\n' >"$K147/m/.git/HEAD"
for _s147 in s1 s2 s3; do
  printf '{"type":"session.start"}\n' >"$D147/session-state/$_s147/events.jsonl"
done
printf 'cwd: /srv/coppool\nclient_name: github/autopilot\n' >"$D147/session-state/s4/workspace.yaml"
printf '# pool\n' >"$ROOT/srv/coppool/AGENTS.md"

# 2026-10-17 session sync round (#153)
# Credential files the session sync research found unflagged: nanobot's
# remote WebUI pairing keys, Agent Zero's plugin configuration (home, native
# and a0_usr volume forms), Cline's cached remote config and webhook config,
# Gemini CLI's /bug-memory heap snapshot, little-coder's legacy config with
# its gist token, and Qwen Code's channel credential files, whose routing
# files (sessions.json, routes.json) stay unflagged. Cline's globalStorage
# cache is collected (its sync queue is evidence), and so is Kilo's log
# directory. Checks follow the default and --no-secrets runs below; the same
# files are in smoke.ps1 under alice.
N153="$H/.nanobot/webui/remote-pairing/11111111-1111-4111-8111-111111111111"
G153="$H/.vscode-server/data/User/globalStorage/saoudrizwan.claude-dev/cache"
T153=plugins/_telegram_integration/config.json
mkdir -p "$N153" "$G153" "$H/agent-zero/main/usr/${T153%/*}" "$H/Desktop/agent-zero/usr/${T153%/*}" \
  "$DV/a0_usr/_data/${T153%/*}" "$DV/a0_usr/_data/usr/${T153%/*}" "$H/Documents/Cline" \
  "$H/.little-coder" "$H/.qwen/channels/weixin" "$H/.qwen/channels/daemon/0123abcd" \
  "$H/.local/share/kilo/log"
printf 'key\n' >"$N153/identity"
printf 'key\n' >"$N153/exchange"
printf '{}\n' >"$N153/request"
printf '{"token":"x"}\n' >"$H/agent-zero/main/usr/$T153"
printf '{"token":"x"}\n' >"$H/Desktop/agent-zero/usr/$T153"
printf '{"token":"x"}\n' >"$DV/a0_usr/_data/$T153"
printf '{"token":"x"}\n' >"$DV/a0_usr/_data/usr/$T153"
printf '{"promptUploading":{}}\n' >"$G153/remote_config_org1.json"
printf '{"items":{}}\n' >"$G153/sync-queue.json"
printf '{"webhook_token":"x"}\n' >"$H/Documents/Cline/webhook_config.json"
printf 'heap\n' >"$H/.gemini/tmp/gem/bug-memory-1792000000000.heapsnapshot"
printf '{"gist_token":"x"}\n' >"$H/.little-coder/config.json"
printf '{"appId":"x","appSecret":"x"}\n' >"$H/.qwen/channels/qqbot-credentials.json"
printf '{"token":"x"}\n' >"$H/.qwen/channels/weixin/account.json"
printf '{}\n' >"$H/.qwen/channels/sessions.json"
printf '{}\n' >"$H/.qwen/channels/daemon/0123abcd/routes.json"
printf 'INFO creating session\n' >"$H/.local/share/kilo/log/2026-10-17T120000.log"

# 2026-10-18 Codex shell snapshots (#160)
# Codex Desktop inside the ChatGPT app (build 26.1013.40934, macOS,
# 2026-10-18) writes .codex/shell_snapshots/<thread uuid>.<unix ns>.sh, the
# user's exported shell environment replayed for the sandbox, so any API key
# the login shell exports lands there. Flagged secret since 1.15.0. Checks
# follow the default and --no-secrets runs below; the same file is in
# smoke.ps1 under alice.
S160="$H/.codex/shell_snapshots/22222222-2222-4222-8222-222222222222.1792000000000000000.sh"
mkdir -p "${S160%/*}"
printf '# Snapshot file\nexport EXAMPLE_API_KEY=x\n' >"$S160"

# 2026-10-19 Codex projectless output directories (#149)
# The ChatGPT desktop app (Windows 2026-10-15, macOS 2026-10-15 and
# 2026-10-18) runs a thread
# with no project in Documents/Codex/<date>/<slug>, with work/ and outputs/
# inside, and records that directory as the rollout cwd. Since 1.16.0 the
# directory is a codex-cli catalog line and discovery drops it as a project;
# bob's first rollout keeps its Documents/app project. Checks follow the
# default run and --inventory below; the same files are in smoke.ps1 under bob.
W149="$B/Documents/Codex/2026-10-18/w"
mkdir -p "$W149/outputs" "$W149/work"
printf '{"cwd":"/Users/bob/Documents/Codex/2026-10-18/w"}\n' \
  >"$B/.codex/sessions/2026/10/03/rollout-2.jsonl"
printf '# report\n' >"$W149/outputs/report.md"
printf 'notes\n' >"$W149/work/notes.txt"

# 2026-10-20 Cursor IDE round on macOS (#6)
# Cursor 3.25.9 and 3.26.13 (macOS, 2026-10-19 and 2026-10-20) keep
# per-account and per-conversation sync stores under AgentStores and one
# directory per in-app update under update-supervisor (events.jsonl, the
# build that ran when, beside the 484 KB supervisor binary). The IDE's
# agent worker embeds a copy of the Agent CLI under agent-cli in
# globalStorage, and ~/.cursor holds canvas type declarations under
# node_modules and a feature-flag cache copied from the server: those are
# excluded; the worker's own files and the agent transcripts stay collected.
# Checks follow the default run below; the same files are in smoke.ps1
# under alice.
C6="$B/Library/Application Support/Cursor"
W6="$C6/User/globalStorage/anysphere.cursor-agent-worker"
mkdir -p "$C6/AgentStores/cursor_agent_stores/u1/.sync" \
  "$C6/AgentStores/cursor_agent_stores/.control/u1/pins" \
  "$C6/update-supervisor/33333333-3333-4333-8333-333333333333" \
  "$W6/agent-cli/.local/share" "$B/.cursor/projects/p/canvases/node_modules" \
  "$B/.cursor/projects/p/agent-transcripts/u"
printf 'sqlite\n' >"$C6/AgentStores/cursor_agent_stores/u1/.sync/index.sqlite"
printf '{"purpose":"foreground"}\n' >"$C6/AgentStores/cursor_agent_stores/.control/u1/pins/1-x.json"
printf '{"type":"supervisor_started"}\n' \
  >"$C6/update-supervisor/33333333-3333-4333-8333-333333333333/events.jsonl"
printf 'binary\n' \
  >"$C6/update-supervisor/33333333-3333-4333-8333-333333333333/cursor-update-supervisor"
printf 'cli\n' >"$W6/agent-cli/.local/share/x"
printf 'worker log\n' >"$W6/cursor-agent-worker-1.log"
printf 'declare const x: number;\n' >"$B/.cursor/projects/p/canvases/node_modules/x.d.ts"
printf '{"type":"turn_ended","status":"success"}\n' \
  >"$B/.cursor/projects/p/agent-transcripts/u/u.jsonl"
printf '{}\n' >"$B/.cursor/statsig-cache.json"

# 2026-10-20 Cursor IDE round on Ubuntu (#236)
# Cursor 3.25.9 (Ubuntu arm64 deb, 2026-10-20) keeps the same sync stores
# under the XDG state directory, .local/state/cursor/agent-stores, not under
# .config/Cursor. Checks follow the default run below; the same files are in
# smoke.ps1 under bob.
L236="$H/.local/state/cursor/agent-stores/cursor_agent_stores"
mkdir -p "$L236/u1/.sync" "$L236/.control/u1/pins"
printf 'sqlite\n' >"$L236/u1/.sync/index.sqlite"
printf '{"purpose":"foreground"}\n' >"$L236/.control/u1/pins/1-x.json"

# 2026-10-21 Cursor IDE round on Windows (#236)
# Cursor 3.26.13 (Windows 11 arm64, per-user installer, 2026-10-21) keeps
# the sync stores under %LOCALAPPDATA%\Cursor\AgentStores, not beside the
# user-data directory in AppData/Roaming, and extracts the worker's Agent
# CLI copy (262.7 MB) under agent-cli in AppData/Roaming/Cursor, which is
# excluded while the worker's log beside it stays collected. Checks follow
# the default run below; the same files are in smoke.ps1 under alice.
S236="$B/AppData/Local/Cursor/AgentStores/cursor_agent_stores"
W236="$B/AppData/Roaming/Cursor/User/globalStorage/anysphere.cursor-agent-worker"
mkdir -p "$S236/u1/.sync" "$S236/.control/u1/pins" "$W236/agent-cli"
printf 'sqlite\n' >"$S236/u1/.sync/index.sqlite"
printf '{"purpose":"foreground"}\n' >"$S236/.control/u1/pins/1-x.json"
printf 'cli\n' >"$W236/agent-cli/x"
printf 'worker log\n' >"$W236/cursor-agent-worker-1.log"
# Cursor 3.26.13 (W21, 2026-10-21) put an installed plugin's marketplace copy
# under .cursor/plugins/cache/<marketplace>/<plugin>/<sha>, excluded like the
# Claude Code and Codex plugin caches; plugins/local beside it is collected.
P236="$B/.cursor/plugins"
mkdir -p "$P236/cache/cursor-public/x/0123abcd" "$P236/local"
printf '{"mcpServers":{}}\n' >"$P236/cache/cursor-public/x/0123abcd/mcp.json"
printf '{}\n' >"$P236/local/x.json"
# Cursor 3.26.16 (W25, 2026-10-21): the update that brought it wrote
# update-supervisor/win32/<installationId>/ with app-ready.json, state.json
# and a copy of inno_updater.exe (3.4 MB), which is excluded.
U236="$B/AppData/Roaming/Cursor/update-supervisor/win32/0000"
mkdir -p "$U236"
printf 'binary\n' >"$U236/inno_updater.exe"
printf '{"currentVersion":"x"}\n' >"$U236/app-ready.json"
printf '{"stage":"x"}\n' >"$U236/state.json"
# 2026-10-21 OpenHands Agent Canvas credentials and workspaces (#218)
# Agent Canvas (OpenHands/OpenHands 8d39305, scripts/mars-credentials.mjs)
# keeps its DigitalOcean connections in mars-credentials.json in the Electron
# user data directory, and Canvas-in-Docker unpacks automation runs under
# ~/.openhands/workspaces (docker/entrypoint.sh), excluded like
# agent-canvas/workspaces; workspaces.json beside it stays collected. Checks
# follow the default run below; the same files are in smoke.ps1 under alice.
M218A="$H/.config/OpenHands Agent Canvas/mars-credentials.json"
M218B="$B/Library/Application Support/OpenHands Agent Canvas/mars-credentials.json"
M218C="$B/AppData/Roaming/OpenHands Agent Canvas/mars-credentials.json"
for _f in "$M218A" "$M218B" "$M218C"; do
  mkdir -p "$(dirname "$_f")"
  printf '{"version":1,"connections":[]}\n' >"$_f"
done
mkdir -p "$H/.openhands/workspaces/run1"
printf 'x\n' >"$H/.openhands/workspaces/run1/f"

# 2026-10-21 Agent Zero source review (#217)
# The WhatsApp bridge's Baileys login state under the install's tmp/ (home,
# Desktop and volume-relative forms), an editor (ACP) chat whose workspace
# and extra folder are discovered as projects, and a computer-use screen
# capture of the A0 CLI connector in the Windows temp directory. Checks
# follow the default and --no-secrets runs below; the same files are in
# smoke.ps1 under alice.
W217=tmp/whatsapp/session/creds.json
C217="$H/agent-zero/main/usr/chats/acp1"
T217="$B/AppData/Local/Temp/_a0_connector/computer_use/ctx1"
mkdir -p "$H/agent-zero/main/${W217%/*}" "$H/Desktop/agent-zero/${W217%/*}" \
  "$DV/a0_usr/_data/${W217%/*}" "$C217" "$ROOT/srv/a0acp" "$ROOT/srv/a0extra" "$T217"
printf '{}\n' >"$H/agent-zero/main/$W217"
printf '{}\n' >"$H/Desktop/agent-zero/$W217"
printf '{}\n' >"$DV/a0_usr/_data/$W217"
printf '{"id": "acp1", "data": {"acp_cwd": "/srv/a0acp", %s}}\n' \
  '"acp_additional_directories": ["/srv/a0extra"]' >"$C217/chat.json"
printf '# acp\n' >"$ROOT/srv/a0acp/AGENTS.md"
printf '# extra\n' >"$ROOT/srv/a0extra/AGENTS.md"
printf 'png\n' >"$T217/0000.png"

# 2026-10-21 framework catalog gaps (#223, #224, #225)
# From source, no real install: CrewAI's project-local .crewai/last_run.json,
# its mark of a run traced to AMP, in a discovered project; difyctl's pending
# device login, login-pending.yml, in its three config directories; and the
# CLAI 2.0 state directory .local/state/pydantic-clai2 with the web
# orchestrator's conversation, a workspace record, its token and session.log,
# and a clone of a remote repository, which is excluded. Checks follow the
# default and --no-secrets runs below; the same files are in smoke.ps1.
mkdir -p "$ROOT/srv/proj/.crewai"
printf '{"execution_id":"x","tier":"ephemeral"}\n' >"$ROOT/srv/proj/.crewai/last_run.json"
for _d224 in .config AppData/Roaming AppData/Local; do
  mkdir -p "$H/$_d224/difyctl"
  printf 'device_code: x\n' >"$H/$_d224/difyctl/login-pending.yml"
done
P225="$H/.local/state/pydantic-clai2"
mkdir -p "$P225/workspaces/registry/ws1" "$P225/workspaces/clones/repo-0123456789/.git"
printf '{}\n' >"$P225/orchestrator.json"
printf '{"id":"ws1"}\n' >"$P225/workspaces/registry/ws1/workspace.json"
printf 'token\n' >"$P225/workspaces/registry/ws1/token"
printf 'log\n' >"$P225/workspaces/registry/ws1/session.log"
printf 'ref: refs/heads/main\n' >"$P225/workspaces/clones/repo-0123456789/.git/HEAD"

# 2026-10-21 Codex worktree cwds and archived threads (#222)
# Codex (source at 4e7b9e2) runs a desktop thread in its own git worktree,
# ~/.codex/worktrees/<4 hex>/<repo>, excluded by the catalog, and moves an
# archived thread's rollout flat into ~/.codex/archived_sessions; Open
# Interpreter keeps the same worktree layout under ~/.openinterpreter.
# Discovery drops a worktree cwd and reads the archive. Checks follow the
# default run below; the same files are in smoke.ps1 (Codex under bob, Open
# Interpreter under alice).
mkdir -p "$B/.codex/archived_sessions" "$ROOT/srv/codexarch" "$B/.codex/worktrees/a1b2/repo" \
  "$H/.openinterpreter/worktrees/c3d4/repo"
printf '{"type":"session_meta","payload":{"cwd":"/srv/codexarch"}}\n' \
  >"$B/.codex/archived_sessions/rollout-2026-10-01T00-00-00-a1.jsonl"
printf '# agents\n' >"$ROOT/srv/codexarch/AGENTS.md"
printf '{"type":"session_meta","payload":{"cwd":"/Users/bob/.codex/worktrees/a1b2/repo"}}\n' \
  >"$B/.codex/sessions/2026/10/03/rollout-3.jsonl"
printf '# agents\n' >"$B/.codex/worktrees/a1b2/repo/AGENTS.md"
printf '{"type":"session_meta","payload":{"cwd":"/home/alice/.openinterpreter/worktrees/c3d4/repo"}}\n' \
  >"$H/.openinterpreter/sessions/2026/10/04/rollout-2026-10-04T00-00-00-u3.jsonl"
printf '# agents\n' >"$H/.openinterpreter/worktrees/c3d4/repo/AGENTS.md"

# 2026-10-21 Cody JetBrains plugin files (#214)
# Source-derived (sourcegraph/cody-public-snapshot at 8e20ac6): the plugin's
# application components in each IDE's options/ directory, ~/.sourcegraph and
# a project's .idea/.sourcegraph settings, and the legacy project-level
# .idea/cody_history.xml. cody_accounts.xml carries customRequestHeaders and
# is flagged; cody_accounts_settings.xml holds only the active account id.
# Checks follow the default and --no-secrets runs below; the same files are
# in smoke.ps1 under alice.
O214="$H/.config/JetBrains/IntelliJIdea2025.2/options"
mkdir -p "$O214" "$H/.sourcegraph" "$ROOT/srv/proj/.idea/.sourcegraph"
printf '<application />\n' >"$O214/cody.xml"
printf '<application />\n' >"$O214/cody_accounts.xml"
printf '<application />\n' >"$O214/cody_accounts_settings.xml"
printf '<application />\n' >"$O214/cody_application_settings.xml"
printf '{}\n' >"$H/.sourcegraph/cody_settings.json"
printf '<project version="4" />\n' >"$ROOT/srv/proj/.idea/cody_history.xml"
printf '{}\n' >"$ROOT/srv/proj/.idea/.sourcegraph/cody_settings.json"

# 2026-10-21 agent worktrees inside a project (#216)
# Gemini CLI's --worktree creates <project>/.gemini/worktrees/<name>
# (google-gemini/gemini-cli 3be3d44, worktreeService.ts) and Qwen Code's
# enter_worktree <project>/.qwen/worktrees/<slug> (QwenLM/qwen-code 5dcf7c7,
# worktreeSessionService.ts): full git checkouts that the project entries
# collected whole. Both are excluded, as .claude/worktrees and
# .kilo/worktrees are; the project's .gemini/settings.json beside them stays
# collected. Checks follow the default run below; the same files are in
# smoke.ps1 under gem.
G216="$ROOT/srv/gem"
mkdir -p "$G216/.gemini/worktrees/w1" "$G216/.qwen/worktrees/w1"
printf 'wt\n' >"$G216/.gemini/worktrees/w1/f"
printf 'wt\n' >"$G216/.qwen/worktrees/w1/f"
printf '{}\n' >"$G216/.gemini/settings.json"

# 2026-10-21 Hermes quick snapshots and desktop connections (#123, #208)
# hermes-agent 86fa9e6 (source only): a quick snapshot under state-snapshots
# holds an older state.db, the only copy of a pruned or deleted session, so
# it is collected, while the credential copies beside it (.env, auth.json,
# the pairing stores) stay flagged by the home-relative secret globs. The
# desktop app's connection.json and connections.json can hold a gateway
# token in plain text and are flagged. Checks follow the default and
# --no-secrets runs below; the same files are in smoke.ps1 under alice.
Q123="$H/.hermes/state-snapshots/20261001-120004-pre-update"
W123="$H/AppData/Local/hermes/state-snapshots/20261001-120004"
mkdir -p "$Q123/pairing" "$W123" "$H/.config/Hermes"
printf 'sqlite\n' >"$Q123/state.db"
printf '{"id":"20261001-120004-pre-update"}\n' >"$Q123/manifest.json"
printf 'KEY=x\n' >"$Q123/.env"
printf '{"providers":{}}\n' >"$Q123/auth.json"
printf '{"42":{"user_name":"u"}}\n' >"$Q123/pairing/telegram-approved.json"
printf 'sqlite\n' >"$W123/state.db"
printf '{"connections":[]}\n' >"$H/.config/Hermes/connections.json"

# 2026-10-21 nanobot workspace cron and triggers (#220)
# nanobot (HKUDS/nanobot at 909b277, source only) keeps its cron jobs and
# local triggers in the workspace, with one run record per run (session
# key, prompt, reply) that outlives the session. The project catalog
# collects the job and trigger files and the runs directories of a
# discovered workspace; the trigger queue (inbox/) is left. Checks follow
# the default run below; the same files are in smoke.ps1 under nanows.
N220="$ROOT/srv/nanows"
mkdir -p "$N220/cron/runs" "$N220/triggers/runs" "$N220/triggers/inbox"
printf '{"jobs":[]}\n' >"$N220/cron/jobs.json"
printf '{"job_id":"j1","status":"ok"}\n' >"$N220/cron/runs/j1_1_ab.json"
printf '{"triggers":[]}\n' >"$N220/triggers/triggers.json"
printf '{"trigger_id":"t1","status":"ok"}\n' >"$N220/triggers/runs/d1.json"
printf '{"id":"d2"}\n' >"$N220/triggers/inbox/d2.json"

# 2026-10-21 OpenClaw source review (#219)
# OpenClaw 2026.10.5 (source, openclaw/openclaw at 146284a) keeps the
# approvals socket token in the legacy exec-approvals.json, and the Docker
# install's ~/.openclaw-auth-profile-secrets holds gateway.env: both are
# flagged, and so is a volume-relative exec-approvals.json. A Gateway clone
# under projects/<16 hex>/<name> is excluded while another projects entry is
# collected, and the volume-relative forms of the clone, plugin-skills and
# agent tmp exclusions prune the same names in a volume (the a0_usr one
# here), whose own projects/<name> stays collected. Checks follow the
# default and --no-secrets runs below; the same files are in smoke.ps1
# under alice.
O219="$H/.openclaw"
C219=0123456789abcdef
V219="$DV/a0_usr/_data"
mkdir -p "$O219/projects/$C219/repo" "$O219/projects/notes" "$H/.openclaw-auth-profile-secrets" \
  "$V219/projects/$C219/repo" "$V219/projects/p219" "$V219/plugin-skills" \
  "$V219/agents/main/agent/tmp" "$V219/agents/main/agent/.tmp"
printf '{"socket":{"token":"x"}}\n' >"$O219/exec-approvals.json"
printf 'OPENAI_API_KEY=x\n' >"$H/.openclaw-auth-profile-secrets/gateway.env"
printf 'clone\n' >"$O219/projects/$C219/repo/README.md"
printf 'notes\n' >"$O219/projects/notes/todo.md"
printf '{"socket":{"token":"x"}}\n' >"$V219/exec-approvals.json"
printf 'clone\n' >"$V219/projects/$C219/repo/README.md"
printf 'project\n' >"$V219/projects/p219/notes.md"
printf 'link\n' >"$V219/plugin-skills/s"
printf 'tmp\n' >"$V219/agents/main/agent/tmp/t"
printf 'tmp\n' >"$V219/agents/main/agent/.tmp/t"

# 2026-10-21 OpenCode and Kilo Code source review (#213, #221)
# Source only, no real install: OpenCode 2.0 (anomalyco/opencode cb07c55)
# writes its background server's password to service.json, or
# service-<channel>.json, in the config and the state directory, keeps the
# Electron desktop app's data in ai.opencode.desktop, .beta or .dev under
# the platform's app data directory with a V8 compile-cache, and keeps a
# temp root that is AppData/Local/Temp/opencode on Windows. Kilo Code
# (Kilo-Org/kilocode 87cc35c) writes its sandbox policy and preference files
# beside its state directory. Checks follow the default and --no-secrets
# runs below; the same files are in smoke.ps1 under alice.
D213="$B/Library/Application Support/ai.opencode.desktop"
K221="$H/.local/state/kilo-sandbox-policy/aa"
mkdir -p "$H/.config/opencode" "$H/.local/state/opencode" "$D213/compile-cache" \
  "$H/.config/ai.opencode.desktop.beta" "$B/AppData/Roaming/ai.opencode.desktop" \
  "$B/AppData/Local/Temp/opencode" "$K221" "$H/.local/state/kilo-sandbox-preference"
printf '{"password":"x"}\n' >"$H/.config/opencode/service.json"
printf '{"password":"x"}\n' >"$H/.local/state/opencode/service-local.json"
printf 'sqlite\n' >"$D213/drafts.sqlite"
printf 'v8\n' >"$D213/compile-cache/x"
printf 'sqlite\n' >"$H/.config/ai.opencode.desktop.beta/drafts.sqlite"
printf 'sqlite\n' >"$B/AppData/Roaming/ai.opencode.desktop/drafts.sqlite"
printf 'tmp\n' >"$B/AppData/Local/Temp/opencode/notes.txt"
printf '{"enabled":true,"mode":"deny","version":1}\n' >"$K221/bb.json"
printf 'false\n' >"$H/.local/state/kilo-sandbox-preference/bb.json"

# 2026-10-21 Qwen Code session registry (#230)
# Qwen Code writes ~/.qwen/sessions/<pid>.json (or <pid>-<8 hex>.json) per
# running session, with ipcToken, the token that admits a connection to the
# session's socket, so the directory is a secret glob. Checks follow the
# default and --no-secrets runs below; the same files are in smoke.ps1 under
# alice.
mkdir -p "$H/.qwen/sessions"
printf '{"sessionId":"x","ipcToken":"x"}\n' >"$H/.qwen/sessions/4242.json"
printf '{"sessionId":"x","ipcToken":"x"}\n' >"$H/.qwen/sessions/4243-0123abcd.json"

# 2026-10-21 Roo Code CLI cloud credentials (#159)
# The Roo Code CLI up to 3.53.0 saved its Roo Code Cloud token in
# ~/.roo/cli-credentials.json (apps/cli/src/lib/storage/credentials.ts at
# Roo-Code v3.53.0); the secret glob flags it. Checks follow the default run
# below; the same file is in smoke.ps1 under alice.
mkdir -p "$H/.roo"
printf '{"token":"not-a-real-token"}\n' >"$H/.roo/cli-credentials.json"

# 2026-10-21 Twinny workspace storage (#215)
# Twinny 4.3.15 (source, twinnydotdev/twinny 0337b265) keeps one
# agent-changes/<uuid>.json record per agent-mode reply that changed files
# in its per-workspace extension storage, workspaceStorage/<id>/
# rjmacarthy.twinny, beside the editor's own workspace.json and
# state.vscdb. The nested twinny entries claim that directory from the
# editor's walk; the files beside it stay vscode. Checks follow the default
# run below; the same files are in smoke.ps1 under alice.
T215="$H/.config/Code/User/workspaceStorage/ws215"
mkdir -p "$T215/rjmacarthy.twinny/agent-changes"
printf '{"id":"c1","root":"/srv/twinproj","createdAt":1,"files":[]}\n' \
  >"$T215/rjmacarthy.twinny/agent-changes/c1.json"
printf '{"folder":"file:///srv/twinproj"}\n' >"$T215/workspace.json"
# The twinny-server forge plugins (GitHub, GitLab, Gitea, Bitbucket) keep
# their saved access tokens beside the watched repositories in
# plugins/<id>/repos.json, flagged secret.
mkdir -p "$H/.twinny/server/plugins/github"
printf '{"version":1,"repos":[],"tokens":[]}\n' >"$H/.twinny/server/plugins/github/repos.json"

# 2026-10-21 project git metadata (#253)
# Every discovered project's .git/HEAD, config, FETCH_HEAD, packed-refs,
# refs/, logs/ and worktrees/ are collected under agent project: the
# remotes with their fetch and push URLs, the checked-out branch, the last
# fetch, the branches and tags, the reflog and the linked worktrees. The
# object store, the index, hooks, LFS objects and submodule repositories
# match no PROJECT_CATALOG line and get no row. Checks follow the default
# run below; the same files are in smoke.ps1 under the project proj.
G253="$ROOT/srv/proj/.git"
mkdir -p "$G253/refs/heads" "$G253/refs/remotes/origin" "$G253/logs/refs/remotes/origin" \
  "$G253/worktrees/wt1" "$G253/objects/ab" "$G253/hooks" "$G253/lfs/objects" "$G253/modules/sub"
printf 'ref: refs/heads/main\n' >"$G253/HEAD"
printf '%s\n' '[core]' '	repositoryformatversion = 0' '	bare = false' \
  '[remote "origin"]' '	url = https://git.example.com/acme/proj.git' \
  '	pushurl = git@git.example.com:acme/proj.git' \
  '	fetch = +refs/heads/*:refs/remotes/origin/*' \
  '[remote "upstream"]' '	url = https://git.example.org/upstream/proj.git' \
  '	fetch = +refs/heads/*:refs/remotes/upstream/*' \
  '[branch "main"]' '	remote = origin' '	merge = refs/heads/main' >"$G253/config"
printf '%s\t\t%s\n' 1111111111111111111111111111111111111111 \
  "branch 'main' of https://git.example.com/acme/proj" >"$G253/FETCH_HEAD"
printf '# pack-refs with: peeled fully-peeled sorted\n%s refs/tags/v1\n' \
  2222222222222222222222222222222222222222 >"$G253/packed-refs"
printf '1111111111111111111111111111111111111111\n' >"$G253/refs/heads/main"
printf '1111111111111111111111111111111111111111\n' >"$G253/refs/remotes/origin/main"
printf '%s %s A <a@example.com> 1759449600 +0000\tclone: from %s\n' \
  0000000000000000000000000000000000000000 1111111111111111111111111111111111111111 \
  https://git.example.com/acme/proj.git >"$G253/logs/HEAD"
printf '%s %s A <a@example.com> 1759449600 +0000\tfetch: fast-forward\n' \
  0000000000000000000000000000000000000000 1111111111111111111111111111111111111111 \
  >"$G253/logs/refs/remotes/origin/main"
printf 'ref: refs/heads/wt1\n' >"$G253/worktrees/wt1/HEAD"
printf '/srv/proj-wt1/.git\n' >"$G253/worktrees/wt1/gitdir"
printf 'DIRC\n' >"$G253/worktrees/wt1/index"
printf 'DIRC\n' >"$G253/worktrees/wt1/index.lock"
printf 'DIRC\n' >"$G253/worktrees/wt1/sharedindex.3333333333333333333333333333333333333333"
mkdir -p "$G253/worktrees/wt1/modules/sub/objects/ab"
printf 'ref: refs/heads/main\n' >"$G253/worktrees/wt1/modules/sub/HEAD"
printf 'object\n' >"$G253/worktrees/wt1/modules/sub/objects/ab/cdef"
printf 'object\n' >"$G253/objects/ab/cdef"
printf 'DIRC\n' >"$G253/index"
printf '#!/bin/sh\n' >"$G253/hooks/pre-commit.sample"
printf 'lfs\n' >"$G253/lfs/objects/x"
printf 'ref: refs/heads/main\n' >"$G253/modules/sub/HEAD"

# 2026-10-23 claude-code Windows round (#256)
# Claude Code 2.1.309 on Windows 11 (real install, 2026-10-23) keeps its
# temp root under the home, AppData/Local/Temp/claude/<slug>/<session>/
# with scratchpad/ and tasks/, and rewrites a project's
# .git/info/exclude, collected as git metadata. Its session daemon keeps
# raw IPC keys and auth values in .claude/daemon/, and .claude/backups/
# holds full copies of .claude.json, as does the older home-level
# .claude.json.backup, so all are secret globs. paste-cache/ holds pasted
# prompt text that history.jsonl names only by hash and is collected;
# plugin-directory-cache-v2.json is a downloaded copy and is excluded.
# Checks follow the default and --no-secrets runs below; the same
# files are in smoke.ps1 under alice and the project proj.
T256="$H/AppData/Local/Temp/claude/C--srv-proj/25625625-6256-4256-8256-256256256256"
mkdir -p "$T256/scratchpad" "$T256/tasks" "$H/.claude/daemon" \
  "$H/.claude/backups" "$H/.claude/paste-cache" "$H/.claude/plugins" "$G253/info"
printf 'scratch\n' >"$T256/scratchpad/notes.txt"
printf 'done\n' >"$T256/tasks/b256b256b.output"
printf '{"oauthAccount":{}}\n' >"$H/.claude.json.backup"
printf '0123456789abcdef0123456789abcdef' >"$H/.claude/daemon/control.key"
printf '0123456789abcdef' >"$H/.claude/daemon/pipe.key"
printf '{"proto":1,"workers":{}}\n' >"$H/.claude/daemon/roster.json"
printf '{"oauthAccount":{}}\n' >"$H/.claude/backups/.claude.json.backup.1792800000000"
printf '{"oauthAccount":{}}\n' >"$H/.claude/backups/.claude.json.corrupted.2026-10-23T17-00-00-000Z"
printf 'pasted text\n' >"$H/.claude/paste-cache/0123456789abcdef.txt"
printf '{"plugins":[]}\n' >"$H/.claude/plugins/plugin-directory-cache-v2.json"
printf '# git ls-files --others --exclude-from=.git/info/exclude\n.claude/scheduled_tasks.lock\n' \
  >"$G253/info/exclude"

# 2026-10-26 claude-code Linux round (#256)
# Claude Code 2.1.310 on Ubuntu 26.04 (real install, 2026-10-25/26) holds
# .local/state/claude/locks/<version>.lock, a JSON lock with acquiredAt,
# execPath, pid and version, while a session runs, and creates
# .cache/claude/staging/ at install; both directories are home-relative on
# Windows too and are collected as claude-code. Checks follow the default
# run below; the same files are in smoke.ps1 under alice.
mkdir -p "$H/.local/state/claude/locks" "$H/.cache/claude/staging"
printf '{"acquiredAt":1792800000000,"execPath":"/x","pid":1,"version":"2.1.310"}\n' \
  >"$H/.local/state/claude/locks/2.1.310.lock"
printf 'staged\n' >"$H/.cache/claude/staging/entry"

# 2026-10-26 claude-code macOS round (#256)
# Claude Code 2.1.310 on macOS 26.6 (real install, 2026-10-26) writes
# ~/Applications/Claude Code URL Handler.app at the first exit: an
# Info.plist registering the claude-cli: URL scheme and Contents/MacOS/claude,
# a symlink to ~/.local/bin/claude, collected as claude-code with the link
# recorded. While an IDE session runs, .claude/ide/<port>.lock holds an
# authToken; while a Remote Control bridge runs,
# .claude/bridge-spawn/<id>/mcp.json holds the session-bound headers of the
# remote MCP endpoint. Both are secret globs, in a relocated config home
# too. Checks follow the default and --no-secrets runs below; the same
# files are in smoke.ps1 under alice.
U256="$H/Applications/Claude Code URL Handler.app/Contents"
S256="bridge-spawn/cse_0123456789abcdef0123"
mkdir -p "$U256/MacOS" "$H/.claude/ide" "$H/.claude/$S256" "$CCW/ide" "$CCW/$S256"
printf '<plist version="1.0"><dict><key>CFBundleURLSchemes</key></dict></plist>\n' \
  >"$U256/Info.plist"
ln -s /home/alice/.local/bin/claude "$U256/MacOS/claude"
for _d256 in "$H/.claude" "$CCW"; do
  printf '{"authToken":"00000000-0000-4000-8000-000000000256","transport":"ws"}\n' \
    >"$_d256/ide/53256.lock"
  printf '{"mcpServers":{"claude-code-remote":{"headers":{"X-Session-UUID":"x"}}}}\n' \
    >"$_d256/$S256/mcp.json"
done
printf 'appended system prompt\n' >"$H/.claude/$S256/append-system-prompt.txt"

run() { # run NAME ARGS...
  _n=$1; shift
  mkdir -p "$OUT/$_n"
  COLLECTOR_SH="$SHELL_UNDER_TEST" "$SHELL_UNDER_TEST" "$SCRIPT" -r "$ROOT" -o "$OUT/$_n" -q --max-file-size 1 "$@" >"$OUT/$_n.stdout" 2>"$OUT/$_n.stderr"
  _rc=$?
  M=$(ls "$OUT/$_n"/*.manifest.jsonl 2>/dev/null)
  # shellcheck disable=SC2034 # A and S are read by the eval'd check strings
  A=$(ls "$OUT/$_n"/*.tar.gz 2>/dev/null)
  # shellcheck disable=SC2034
  S=$(ls "$OUT/$_n"/*.collection.json 2>/dev/null)
  return "$_rc"
}
# On a case-insensitive filesystem a path is recorded in its first catalog
# spelling (#29), so the lookup ignores case there.
row() {
  if [ "$CASE_INSENSITIVE" = 1 ]; then grep -iF "\"path\":\"$1\"" "$M"; else grep -F "\"path\":\"$1\"" "$M"; fi | head -n1
}
# shellcheck disable=SC2317,SC2329 # called from the eval'd check strings
status_of() { row "$1" | sed 's/.*"status":"\([^"]*\)".*/\1/'; }

printf '== shell: %s (%s)\n' "$SHELL_UNDER_TEST" "$(command -v "$SHELL_UNDER_TEST")"

# ---- default run ----------------------------------------------------------
run default; check "exit code 0" "[ $? -eq 0 ]"
check "archive exists" "[ -s \"\$A\" ]"
check "sha256 sidecar matches" "[ \"\$(cut -d' ' -f1 \"\$A.sha256\")\" = \"\$(sha256sum \"\$A\" | cut -d' ' -f1)\" ]"
check "transcript collected" "[ \"\$(status_of \"$ROOT/home/alice/.claude/projects/-srv-proj/s1.jsonl\")\" = collected ]"
check "transcript hash correct" "[ \"\$(row \"$ROOT/home/alice/.claude/projects/-srv-proj/s1.jsonl\" | sed 's/.*\"sha256\":\"\([^\"]*\)\".*/\1/')\" = \"\$(sha256sum \"$ROOT/home/alice/.claude/projects/-srv-proj/s1.jsonl\" | cut -d' ' -f1)\" ]"
check "secret collected and flagged" "row \"$ROOT/home/alice/.claude/.credentials.json\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "antigravity token flagged secret" "row \"$ROOT/home/alice/.gemini/antigravity-cli/antigravity-oauth-token\" | grep -q '\"secret\":true'"
check "cache dir skipped_excluded with size" "row \"$ROOT/home/alice/.claude/cache\" | grep -q '\"type\":\"dir\",\"size\":[1-9][0-9]*.*\"status\":\"skipped_excluded\"'"
check "cache contents not collected" "! grep -q 'cache/junk.bin' \"\$M\""
check "nested entry attributed to its own agent" "row \"$ROOT/home/alice/.gemini/antigravity-cli/conversations/c1.db\" | grep -q '\"agent\":\"antigravity\"'"
check "nested entry collected exactly once" "[ \"\$(grep -c 'antigravity-cli/conversations/c1.db' \"\$M\")\" = 1 ]"
check "enclosing entry still attributed to gemini-cli" "row \"$ROOT/home/alice/.gemini/projects.json\" | grep -q '\"agent\":\"gemini-cli\"'"
check "antigravity bin excluded" "[ \"\$(status_of \"$ROOT/home/alice/.gemini/antigravity-cli/bin\")\" = skipped_excluded ]"
check "ollama model blobs excluded" "[ \"\$(status_of \"$ROOT/home/ollama/.ollama/models/blobs\")\" = skipped_excluded ]"
check "ollama history collected (service account home)" "[ \"\$(status_of \"$ROOT/home/ollama/.ollama/history\")\" = collected ]"
check "oversized file skipped_size" "[ \"\$(status_of \"$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/state.vscdb\")\" = skipped_size ]"
check "ms-python globalStorage excluded" "[ \"\$(status_of \"$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/ms-python.python\")\" = skipped_excluded ]"
check "symlink recorded with target" "row \"$ROOT/home/alice/.gemini/antigravity-cli/cli.log\" | grep -q '\"type\":\"symlink\".*\"status\":\"symlink\",\"target\":\"log/cli-1.log\"'"
check "symlink present in archive" "tar -tzf \"\$A\" | grep -q 'antigravity-cli/cli.log'"
check "weird filename collected" "grep -q 'weird \\\\\"name\\\\\" with spaces \\\\\\\\ bs.txt.*\"status\":\"collected\"' \"\$M\""
check "project from history.jsonl collected" "[ \"\$(status_of \"$ROOT/srv/proj/CLAUDE.md\")\" = collected ]"
check "project .claude settings collected" "[ \"\$(status_of \"$ROOT/srv/proj/.claude/settings.local.json\")\" = collected ]"
check "project owner attributed" "row \"$ROOT/srv/proj/CLAUDE.md\" | grep -q '\"user\":\"alice\"'"
# 2026-10-14 project files attributed to their agent (#104)
check "project .claude file attributed to claude-code" "row \"$ROOT/srv/proj/.claude/settings.local.json\" | grep -q '\"home\":\"$ROOT/srv/proj\",\"agent\":\"claude-code\".*\"status\":\"collected\"'"
check "shared project AGENTS.md keeps agent project" "row \"$ROOT/srv/droid/AGENTS.md\" | grep -q '\"home\":\"$ROOT/srv/droid\",\"agent\":\"project\".*\"status\":\"collected\"'"
check "project from cursor workspace.json collected" "[ \"\$(status_of \"$ROOT/Users/bob/Documents/app/.cursorrules\")\" = collected ]"
check "bob (no passwd entry) found via /Users glob" "grep -q '\"user\":\"bob\"' \"\$M\""
check "nobody home skipped" "! grep -q '\"home\":\"$ROOT/nonexistent\"' \"\$M\""
check "shell history not collected" "! grep -q '.bash_history' \"\$M\""
check "continue sessions.json discovers project" "[ \"\$(status_of \"$ROOT/srv/cont/.continuerc.json\")\" = collected ]"
check "continue globalContext flagged secret" "row \"$ROOT/home/alice/.continue/index/globalContext.json\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "continue lancedb excluded" "[ \"\$(status_of \"$ROOT/home/alice/.continue/index/lancedb\")\" = skipped_excluded ]"
check "crush projects.json discovers project-local crush.db" "[ \"\$(status_of \"$ROOT/srv/crushproj/.crush/crush.db\")\" = collected ]"
check "gemini projects.json / .project_root discovers project" "[ \"\$(status_of \"$ROOT/srv/gem/GEMINI.md\")\" = collected ]"
check "cline session cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/clineproj/.clinerules\")\" = collected ]"
check "cline providers.json flagged secret" "row \"$ROOT/home/alice/.cline/data/settings/providers.json\" | grep -q '\"secret\":true'"
check "opencode auth.json flagged secret" "row \"$ROOT/home/alice/.local/share/opencode/auth.json\" | grep -q '\"secret\":true'"
check "home .env not collected" "[ -z \"\$(row \"$ROOT/home/alice/.env\")\" ]"
check "claude desktop config.json flagged secret" "row \"$ROOT/Users/bob/Library/Application Support/Claude/config.json\" | grep -q '\"secret\":true'"
check "claude desktop mcp config flagged secret" "row \"$ROOT/Users/bob/Library/Application Support/Claude/claude_desktop_config.json\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "claude desktop Cache excluded" "[ \"\$(status_of \"$ROOT/Users/bob/Library/Application Support/Claude/Cache\")\" = skipped_excluded ]"
check "zed extensions excluded via [Zz]ed glob" "[ \"\$(status_of \"$ROOT/Users/bob/Library/Application Support/Zed/extensions\")\" = skipped_excluded ]"
check "zed threads.db collected" "[ \"\$(status_of \"$ROOT/Users/bob/Library/Application Support/Zed/threads/threads.db\")\" = collected ]"
check "zed settings.json flagged secret" "row \"$ROOT/Users/bob/.config/zed/settings.json\" | grep -q '\"secret\":true'"
check "cline globalStorage attributed to cline, not cursor" "row \"$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/state/taskHistory.json\" | grep -q '\"agent\":\"cline\"'"
check "cline globalStorage collected exactly once" "[ \"\$(grep -c 'Cursor/User/globalStorage/saoudrizwan.claude-dev/state/taskHistory.json' \"\$M\")\" = 1 ]"
check "cursor state.vscdb still attributed to cursor" "row \"$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/state.vscdb\" | grep -q '\"agent\":\"cursor\"'"
check "factory session index not swallowed by cache exclusion" "[ \"\$(status_of \"$ROOT/home/alice/.factory/cache/session-index/index.db\")\" = collected ]"
check "factory cache sounds excluded" "[ \"\$(status_of \"$ROOT/home/alice/.factory/cache/sounds\")\" = skipped_excluded ]"
check "factory session cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/droid/AGENTS.md\")\" = collected ]"
check "kiro power mcp.json collected and flagged" "row \"$ROOT/home/alice/.kiro/powers/installed/p1/mcp.json\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "kiro cli session cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/kiroproj/.kiroignore\")\" = collected ]"
check "vscode-server User dir collected as vscode" "row \"$ROOT/home/alice/.vscode-server/data/User/globalStorage/state.vscdb\" | grep -q '\"agent\":\"vscode\"'"
check "cline inside vscode-server attributed to cline" "row \"$ROOT/home/alice/.vscode-server/data/User/globalStorage/saoudrizwan.claude-dev/state/taskHistory.json\" | grep -q '\"agent\":\"cline\"'"
check "vscode-server taskHistory discovers project" "[ \"\$(status_of \"$ROOT/srv/remoteproj/.clinerules\")\" = collected ]"
check "antigravity-ide attributed to antigravity" "row \"$ROOT/home/alice/.gemini/antigravity-ide/conversations/i1.db\" | grep -q '\"agent\":\"antigravity\"'"
check "gemini config dir attributed to antigravity" "row \"$ROOT/home/alice/.gemini/config/mcp_config.json\" | grep -q '\"agent\":\"antigravity\"'"
check "antigravity history workspace discovers project" "[ \"\$(status_of \"$ROOT/srv/agyproj/.antigravityignore\")\" = collected ]"
check "cursor auth.json flagged secret" "row \"$ROOT/home/alice/.cursor/auth.json\" | grep -q '\"secret\":true'"
check "cursor project mcp-auth.json flagged secret" "row \"$ROOT/home/alice/.cursor/projects/-srv-proj/mcp-auth.json\" | grep -q '\"secret\":true'"
check "copilot pkg excluded" "[ \"\$(status_of \"$ROOT/home/alice/.copilot/pkg\")\" = skipped_excluded ]"
check "copilot config.json flagged secret" "row \"$ROOT/home/alice/.copilot/config.json\" | grep -q '\"secret\":true'"
check "copilot workspace.yaml cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/copproj/AGENTS.md\")\" = collected ]"
check "claude device keys flagged secret" "row \"$ROOT/home/alice/.claude/.device-keys.json\" | grep -q '\"secret\":true'"
check "claude image-cache excluded" "[ \"\$(status_of \"$ROOT/home/alice/.claude/image-cache\")\" = skipped_excluded ]"
check "amp history cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/ampproj/.amp/settings.json\")\" = collected ]"
check "windsurf transcripts collected" "row \"$ROOT/home/alice/.windsurf/transcripts/t1.jsonl\" | grep -q '\"agent\":\"windsurf\".*\"status\":\"collected\"'"
check "project-level kilo worktrees excluded" "[ \"\$(status_of \"$ROOT/srv/kiloproj/.kilo/worktrees\")\" = skipped_excluded ]"
check "ollama desktop app dir collected" "[ \"\$(status_of \"$ROOT/Users/bob/Library/Application Support/Ollama/db.sqlite\")\" = collected ]"
check "cline taskHistory in globalStorage discovers project" "[ \"\$(status_of \"$ROOT/Users/bob/clineproj/.clinerules\")\" = collected ]"
check "cline checkpoints in globalStorage excluded" "[ \"\$(status_of \"$ROOT/Users/bob/Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/checkpoints\")\" = skipped_excluded ]"
# 1.4.0 catalog round (2026-10-04)
printf '%s\n' "$CASES14" >"$WORK/cases14"
while IFS='|' read -r _k _a _r; do
  [ -n "$_r" ] || continue
  _row=$(row "$H/$_r")
  case "$_k" in
    excl|exclf) case "$_row" in *'"status":"skipped_excluded"'*) ok "excluded: $_r" ;; *) bad "excluded: $_r" ;; esac ;;
    secret) case "$_row" in *'"secret":true,"status":"collected"'*) ok "secret: $_r" ;; *) bad "secret: $_r" ;; esac ;;
    agent) case "$_row" in *"\"agent\":\"$_a\""*'"status":"collected"'*) ok "$_a: $_r" ;; *) bad "$_a: $_r" ;; esac ;;
  esac
done <"$WORK/cases14"
check "pearai lowercase .config/pearai collected" "[ \"\$(grep -ci '/.config/pearai/User/globalStorage/state.vscdb\"' \"\$M\")\" = 1 ]"
check "cody nested globalStorage collected exactly once" "[ \"\$(grep -c 'sourcegraph.cody-ai/symf/indexroot/meta.json' \"\$M\")\" = 1 ]"
check "twinny nested globalStorage collected exactly once" "[ \"\$(grep -c 'globalStorage/rjmacarthy.twinny/twinny-providers.json' \"\$M\")\" = 1 ]"
check "little-coder history nested in .pi collected exactly once" "[ \"\$(grep -c 'little-coder-prompt-history.json' \"\$M\")\" = 1 ]"
check "hermes installer checkout excluded but its .env kept" "[ \"\$(status_of \"$H/.hermes/hermes-agent/hermes_cli\")\" = skipped_excluded ] && [ \"\$(status_of \"$H/.hermes/hermes-agent/.env\")\" = collected ]"
check "openclaw .clawdbot rename symlink recorded" "row \"$B/.clawdbot\" | grep -q '\"agent\":\"openclaw\".*\"type\":\"symlink\".*\"status\":\"symlink\",\"target\":\".openclaw\"'"
check "hermes checkpoint workdir discovers project" "row \"$ROOT/srv/hermesproj/.hermes.md\" | grep -q '\"user\":\"alice\".*\"status\":\"collected\"'"
check "letta sessions.jsonl project discovers project" "[ \"\$(status_of \"$ROOT/srv/lettaproj/.letta/settings.json\")\" = collected ]"
check "project .letta/settings.json flagged secret (accepted overmatch)" "row \"$ROOT/srv/lettaproj/.letta/settings.json\" | grep -q '\"secret\":true'"
check "letta local backend messages cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/lettaproj2/AGENTS.md\")\" = collected ]"
check "pi session cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/piproj/.pi/settings.json\")\" = collected ]"
check "pi misplaced session cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/piproj2/AGENTS.md\")\" = collected ]"
check "pi trust.json keys discover project" "[ \"\$(status_of \"$ROOT/srv/pitrust/pi-session-2026-10-04.html\")\" = collected ]"
check "pi crashes.json cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/picrash/AGENTS.md\")\" = collected ]"
check "pi experimental meta cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/piexp/AGENTS.md\")\" = collected ]"
check "open-interpreter rollout cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/oiproj/.openinterpreter/rules/r.md\")\" = collected ]"
check "open-interpreter archived rollout cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/oiarch/.codewhale/notes.md\")\" = collected ]"
check "openhands workspaces.json path discovers project" "[ \"\$(status_of \"$ROOT/srv/ohproj/.openhands/setup.sh\")\" = collected ]"
check "openhands canvas dev conversation discovers project" "[ \"\$(status_of \"$ROOT/srv/ohdev/AGENTS.md\")\" = collected ]"
check "openhands canvas conversation discovers project" "[ \"\$(status_of \"$ROOT/srv/ohcanvas/AGENTS.md\")\" = collected ]"
check "openhands cli base_state discovers project" "[ \"\$(status_of \"$ROOT/srv/ohcli/AGENTS.md\")\" = collected ]"
check "pearai sessions.json discovers project" "[ \"\$(status_of \"$ROOT/srv/pearproj/.pearairc.json\")\" = collected ]"
check "project .pearai-agent/mcp.json flagged secret" "row \"$ROOT/srv/pearproj/.pearai-agent/mcp.json\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "openclaw JSON5 workspace discovers project" "[ \"\$(status_of \"$ROOT/srv/clawws/SOUL.md\")\" = collected ]"
check "openclaw JSON5 agentDir discovers project" "[ \"\$(status_of \"$ROOT/srv/clawagent/AGENTS.md\")\" = collected ]"
check "openclaw legacy clawdbot.json discovers project" "[ \"\$(status_of \"$ROOT/srv/clawlegacy/IDENTITY.md\")\" = collected ]"
check "openclaw profile config discovers project" "[ \"\$(status_of \"$ROOT/srv/clawprofile/MEMORY.md\")\" = collected ]"
check "nanobot .workspace marker discovers project" "[ \"\$(status_of \"$ROOT/srv/nanows/HEARTBEAT.md\")\" = collected ]"
check "nanobot instance config workspace discovers project" "[ \"\$(status_of \"$ROOT/srv/nanocfg/memory/MEMORY.md\")\" = collected ]"
check "tabby config.toml file:// git_url discovers project" "[ \"\$(status_of \"$ROOT/srv/tabbyproj/AGENTS.md\")\" = collected ]"
check "twinny manifest common prefix discovers project" "[ \"\$(status_of \"$ROOT/srv/twinproj/AGENTS.md\")\" = collected ]"
# 1.5.0 Docker volumes (2026-10-04)
A0="$DV/a0_usr/_data"
check "docker volume file collected as agent-zero, user docker" "row \"$A0/chats/ctx1/chat.json\" | grep -q '\"user\":\"docker\",\"home\":\"$A0\",\"agent\":\"agent-zero\".*\"status\":\"collected\"'"
check "docker volume file archived under fs/<original path>" "tar -tzf \"\$A\" | grep -q '^./fs/var/lib/docker/volumes/a0_usr/_data/chats/ctx1/chat.json\$'"
check "docker volume .env flagged secret (volume-relative)" "row \"$A0/.env\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "docker volume tmp/playwright excluded (volume-relative)" "[ \"\$(status_of \"$A0/tmp/playwright\")\" = skipped_excluded ]"
check "unmatched volume recorded skipped_unmatched_volume with size" "row \"$DV/pgdata/_data\" | grep -q '\"user\":\"docker\".*\"type\":\"dir\",\"size\":[1-9][0-9]*.*\"status\":\"skipped_unmatched_volume\"'"
check "unmatched volume contents not collected" "! grep -q 'pgdata/_data/x' \"\$M\""
check "volumes dir metadata.db not collected" "! grep -q 'volumes/metadata.db' \"\$M\""
check "rootless volume collected as tabby" "row \"$H/.local/share/docker/volumes/tabby_data/_data/events/2026-10-01.json\" | grep -q '\"user\":\"docker\".*\"agent\":\"tabby\".*\"status\":\"collected\"'"
check "summary counts skipped_unmatched_volume" "grep -q '\"skipped_unmatched_volume\": 1' \"\$S\""
check "summary docker counts" "grep -q '\"docker\": {\"volumes_found\": 3, \"volumes_collected\": 2, \"unreadable\": 0' \"\$S\""
check "summary no_docker option false" "grep -q '\"no_docker\": false' \"\$S\""
check "stdout docker line" "grep -q '^docker:     3 volumes found, 2 collected, 0 unreadable\$' \"$OUT/default.stdout\""
# 2026-10-04 summary: only homes with manifest rows are counted and logged; sizes are also human-readable
check "home without artifacts still listed in users" "tr -d '\n' <\"\$S\" | grep -q '\"users\": \\[[^]]*\"dave\"'"
check "home without artifacts not in users_with_artifacts" "grep -q '\"users_with_artifacts\": \\[\"' \"\$S\" && ! grep '\"users_with_artifacts\"' \"\$S\" | grep -q dave"
check "stdout users counts users_with_artifacts" "[ \"\$(sed -n 's/^users: *//p' \"$OUT/default.stdout\")\" = \"\$(grep '\"users_with_artifacts\"' \"\$S\" | tr ',' '\\n' | grep -c '\"')\" ]"
check "log has no progress line for a home without artifacts" "! grep -q 'User dave' \"$OUT\"/default/*.log && grep -q 'User alice' \"$OUT\"/default/*.log"
check "stdout size is human-readable" "grep -q '^size:       [0-9]* ([0-9.]* \\(B\\|KiB\\|MiB\\))\$' \"$OUT/default.stdout\""
check "stdout collected bytes are human-readable" "grep -q '^collected:  [0-9]* files, [0-9]* bytes ([0-9.]* \\(B\\|KiB\\|MiB\\))\$' \"$OUT/default.stdout\""
check "log done line keeps size and sha256" "grep -q ' done: .* ([0-9]* bytes, sha256 [0-9a-f]\\{64\\})\$' \"$OUT\"/default/*.log"
# 2026-10-04 Muse Code
printf '%s\n' "$CASES_MUSE" >"$WORK/casesmuse"
while IFS='|' read -r _k _a _r; do
  [ -n "$_r" ] || continue
  _row=$(row "$H/$_r")
  case "$_k" in
    excl|exclf) case "$_row" in *'"agent":"muse-code"'*'"status":"skipped_excluded"'*) ok "excluded: $_r" ;; *) bad "excluded: $_r" ;; esac ;;
    secret) case "$_row" in *'"agent":"muse-code"'*'"secret":true,"status":"collected"'*) ok "secret: $_r" ;; *) bad "secret: $_r" ;; esac ;;
    agent) case "$_row" in *"\"agent\":\"$_a\""*'"status":"collected"'*) ok "$_a: $_r" ;; *) bad "$_a: $_r" ;; esac ;;
  esac
done <"$WORK/casesmuse"
check "muse windows binary excluded with its size" "row \"$H/AppData/Local/Programs/muse/muse-bin-1.4.2-R1.exe\" | grep -q '\"type\":\"file\",\"size\":2,.*\"status\":\"skipped_excluded\"'"
check "muse .local/bin glob leaves other tools alone" "! grep -q '/.local/bin/othertool\"' \"\$M\""
check "muse trust.json projects key discovers project" "row \"$ROOT/srv/musetrust/AGENTS.md\" | grep -q '\"user\":\"alice\".*\"status\":\"collected\"'"
check "muse session.jsonl workspace_root discovers project" "row \"$ROOT/srv/museproj/.muse/hooks.json\" | grep -q '\"user\":\"alice\",\"home\":\"$ROOT/srv/museproj\",\"agent\":\"muse-code\".*\"status\":\"collected\"'"
check "muse project .muse/worktrees excluded" "[ \"\$(status_of \"$ROOT/srv/museproj/.muse/worktrees\")\" = skipped_excluded ]"
# 2026-10-04 relocated Claude Code home
check "relocated claude home session collected as claude-code" "row \"$CCW_S\" | grep -q '\"agent\":\"claude-code\".*\"status\":\"collected\"'"
check "relocated claude home history collected as claude-code" "row \"$CCW/history.jsonl\" | grep -q '\"agent\":\"claude-code\".*\"status\":\"collected\"'"
check "relocated claude home credentials flagged secret" "row \"$CCW/.credentials.json\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"'"
check "relocated claude home .claude.json flagged secret" "row \"$CCW/.claude.json\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"'"
# 2026-10-23 (#256)
check "#256 relocated claude home session key, daemon files and backup flagged secret" "row \"$CCW_K\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"' && row \"$CCW/daemon/control.key\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"' && row \"$CCW/daemon/roster.json\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"' && row \"$CCW/backups/.claude.json.backup.1792800000000\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"'"
check "claude-code-router not collected" "! grep -q '/.claude-code-router/' \"\$M\""
check "relocated .claude.json projects key discovers project" "row \"$ROOT/srv/ccwork/.claude/settings.json\" | grep -q '\"user\":\"alice\".*\"agent\":\"claude-code\".*\"status\":\"collected\"'"
check "relocated history.jsonl discovers project" "row \"$ROOT/srv/cchist/.claude/settings.json\" | grep -q '\"user\":\"alice\".*\"agent\":\"claude-code\".*\"status\":\"collected\"'"
check "no live snapshot directory" "! tar -tzf \"\$A\" | grep -q '^./live/'"
check "summary has no no_live option" "! grep -q no_live \"\$S\""
check "manifest and summary inside archive" "tar -tzf \"\$A\" | grep -q '^./manifest.jsonl' && tar -tzf \"\$A\" | grep -q '^./collection.json'"
check "staging removed" "[ -z \"\$(ls -d \"$OUT/default\"/.stage-* 2>/dev/null)\" ]"
check "no copy errors" "grep -q '\"error_copy\": 0' \"\$S\""
if command -v python3 >/dev/null 2>&1; then
  check "manifest is valid JSONL" "python3 -c 'import json,sys; [json.loads(l) for l in open(sys.argv[1])]' \"\$M\""
  check "summary is valid JSON" "python3 -c 'import json,sys; json.load(open(sys.argv[1]))' \"\$S\""
  check "archived file bytes match staged hash" "cd \"\$WORK\" && mkdir -p x && tar -xzf \"\$A\" -C x && python3 - \"\$M\" x <<'PY'
import json,sys,hashlib,os
m,root=sys.argv[1],sys.argv[2]; n=0
for l in open(m):
    r=json.loads(l)
    if r['status']!='collected' or not r['archive_path']: continue
    p=os.path.join(root,r['archive_path'])
    assert hashlib.sha256(open(p,'rb').read()).hexdigest()==r['sha256'], p
    assert os.path.getsize(p)==r['size'], p
    n+=1
assert n>5
PY"
fi

# 2026-10-04 bug round: #29
# shellcheck disable=SC2317,SC2329 # called from the eval'd check strings
count_of() { grep -ci "/$1\"" "$M"; }
if [ "$CASE_INSENSITIVE" = 1 ]; then
  printf 'note: %s is case-insensitive; checking the folded layout\n' "$WORK"
  check "#29 case variants of one directory collected once" "[ \"\$(count_of case29-upper.json)\" = 1 ] && [ \"\$(count_of case29-lower.json)\" = 1 ]"
  check "#29 first catalog spelling wins" "grep -qF '\"path\":\"$H/.config/PearAI/User/case29-lower.json\"' \"\$M\""
  check "#29 nested case variant collected once under the nested entry" "[ \"\$(count_of case29-editor.json)\" = 1 ] && grep -qF '\"path\":\"$H/.config/cursor/User/case29-editor.json\"' \"\$M\""
  check "#29 dropped variant logged" "grep -q '/.config/pearai/User: same file as .*/.config/PearAI/User (case-insensitive filesystem)' \"$OUT\"/default/*.log"
else
  check "#29 PearAI and pearai are distinct here and both collected" "[ \"\$(status_of \"$H/.config/PearAI/User/case29-upper.json\")\" = collected ] && [ \"\$(status_of \"$H/.config/pearai/User/case29-lower.json\")\" = collected ] && [ \"\$(count_of case29-upper.json)\" = 1 ] && [ \"\$(count_of case29-lower.json)\" = 1 ]"
  check "#29 nested Cursor/User distinct from cursor and both collected" "row \"$H/.config/cursor/case29-cli.json\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"' && row \"$H/.config/Cursor/User/case29-editor.json\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"' && [ \"\$(count_of case29-editor.json)\" = 1 ]"
  check "#29 nothing folded on a case-sensitive filesystem" "! grep -q 'case-insensitive filesystem' \"$OUT\"/default/*.log"
fi

# 2026-10-06 Ollama (#44)
check "ollama model manifest collected" "row \"$OLM\" | grep -q '\"agent\":\"ollama\".*\"status\":\"collected\"'"
check "ollama blob not collected" "! grep -q 'blobs/sha256-abc' \"\$M\""
check "ollama /usr/share/ollama home from passwd collected" "row \"$ROOT/usr/share/ollama/.ollama/history\" | grep -q '\"user\":\"svc-ollama\",\"home\":\"$ROOT/usr/share/ollama\",\"agent\":\"ollama\".*\"status\":\"collected\"'"
check "ollama /usr/share/ollama blobs excluded" "[ \"\$(status_of \"$ROOT/usr/share/ollama/.ollama/models/blobs\")\" = skipped_excluded ]"

# 2026-10-06 frameworks sweep (#64)
printf '%s\n' "$CASES_FW" >"$WORK/casesfw"
while IFS='|' read -r _k _a _r; do
  [ -n "$_r" ] || continue
  _row=$(row "$H/$_r")
  case "$_k" in
    excl|exclf) case "$_row" in *'"status":"skipped_excluded"'*) ok "excluded: $_r" ;; *) bad "excluded: $_r" ;; esac ;;
    secret) case "$_row" in *'"secret":true,"status":"collected"'*) ok "secret: $_r" ;; *) bad "secret: $_r" ;; esac ;;
    agent) case "$_row" in *"\"agent\":\"$_a\""*'"status":"collected"'*) ok "$_a: $_r" ;; *) bad "$_a: $_r" ;; esac ;;
  esac
done <"$WORK/casesfw"
check "crewai mid-path wildcard leaves other files in the project dir alone" "! grep -q '/.local/share/myproj/unrelated.txt\"' \"\$M\""
check "crewai lowercase AppData/Local/crewai collected through the class" "row \"$B/AppData/Local/crewai/myproj/latest_kickoff_task_outputs.db\" | grep -q '\"agent\":\"crewai\".*\"status\":\"collected\"'"
check "crewai lowercase credentials flagged secret through the class" "row \"$B/AppData/Local/crewai/credentials/tokens.enc\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "camel-ai narrow lines leave Apache Camel JBang files alone" "! grep -q '/.camel/4242-status.json\"' \"\$M\""
check "legacy open-interpreter space-named dir collected once" "[ \"\$(grep -c '/.config/Open Interpreter Terminal/conversations/old.json\"' \"\$M\")\" = 1 ]"

# 2026-10-11 Claude Desktop Linux deb and Claude Code 2.1.295 session keys (#73, #76)
check "#73 Linux spaces-present link-key flagged secret" "row \"$C76/spaces-present/0a0a0a0a/0b0b0b0b/link-key\" | grep -q '\"agent\":\"claude-desktop\".*\"secret\":true,\"status\":\"collected\"'"
check "#76 Claude Code sessions/<pid>.<hash>.key flagged secret" "row \"$K76\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"'"
check "#76 Claude Code sessions/<pid>.json collected, not secret" "row \"$H/.claude/sessions/4242.json\" | grep -q '\"agent\":\"claude-code\".*\"secret\":false,\"status\":\"collected\"'"
check "#73 Linux git-shadow/cli-temp-roots.json collected as claude-desktop" "row \"$C76/git-shadow/cli-temp-roots.json\" | grep -q '\"agent\":\"claude-desktop\".*\"secret\":false,\"status\":\"collected\"'"
check "#73 Linux logs/main.log inside the data dir collected as claude-desktop" "row \"$C76/logs/main.log\" | grep -q '\"agent\":\"claude-desktop\".*\"secret\":false,\"status\":\"collected\"'"
check "#73 Linux Code-tab session record collected as claude-desktop" "row \"$C76/claude-code-sessions/$O76/local_76767676-7676-4676-8676-767676767676.json\" | grep -q '\"agent\":\"claude-desktop\".*\"secret\":false,\"status\":\"collected\"'"
check "#73 Linux claude-code excluded, downloaded CLI not in the manifest" "[ \"\$(status_of \"$C76/claude-code\")\" = skipped_excluded ] && ! grep -q '/9b32b47ec4b3/' \"\$M\""

# 2026-10-11 Claude Code CLI cache directory (#81)
check "#81 Claude Code CLI cache MCP log collected as claude-code" "row \"$F81\" | grep -q '\"agent\":\"claude-code\".*\"status\":\"collected\"'"
check "#81 Claude Code CLI cache MCP log not secret" "row \"$F81\" | grep -q '\"secret\":false,\"status\":\"collected\"'"
check "#81 Claude Code CLI cache Windows Cache child collected as claude-code" "row \"$W81\" | grep -q '\"agent\":\"claude-code\".*\"status\":\"collected\"'"

# 2026-10-13 Antigravity desktop app (#83, #84)
check "#83 Antigravity app conversation collected as antigravity" "row \"$G83/conversations/a1.db\" | grep -q '\"agent\":\"antigravity\".*\"status\":\"collected\"'"
check "#83 Antigravity app crashes/ collected" "[ \"\$(status_of \"$G83/crashes/crash_1.log\")\" = collected ]"
check "#84 Antigravity plugin token.json flagged secret" "row \"$G83/plugin_data/gdocs/token.json\" | grep -q '\"agent\":\"antigravity\".*\"secret\":true,\"status\":\"collected\"'"
check "#83 Antigravity plugin binary excluded" "[ \"\$(status_of \"$G83/plugin_data/gdocs/bin\")\" = skipped_excluded ] && ! grep -q 'gdocs/bin/gdocs-1\"' \"\$M\""
check "#83 Antigravity app bin excluded" "[ \"\$(status_of \"$G83/bin\")\" = skipped_excluded ] && ! grep -q 'antigravity/bin/webm_encoder\"' \"\$M\""
check "#83 Antigravity marketplace cache excluded, other cache files collected" "[ \"\$(status_of \"$G83/cache/marketplaces\")\" = skipped_excluded ] && [ \"\$(status_of \"$G83/cache/last_conversations.json\")\" = collected ]"
check "#83 Antigravity Electron app_storage.json collected as antigravity" "row \"$E83/app_storage.json\" | grep -q '\"agent\":\"antigravity\".*\"status\":\"collected\"'"
check "#83 Antigravity Electron Cache and Code Cache excluded" "[ \"\$(status_of \"$E83/Cache\")\" = skipped_excluded ] && [ \"\$(status_of \"$E83/Code Cache\")\" = skipped_excluded ] && ! grep -q 'Antigravity/Cache/data_0\"' \"\$M\" && ! grep -q 'Antigravity/Code Cache/js/x\"' \"\$M\""
check "#83 Antigravity Library/Logs main.log collected as antigravity" "row \"$H/Library/Logs/Antigravity/main.log\" | grep -q '\"agent\":\"antigravity\".*\"status\":\"collected\"'"
check "#83 Antigravity Windows app_storage.json collected as antigravity" "row \"$W83/app_storage.json\" | grep -q '\"agent\":\"antigravity\".*\"status\":\"collected\"'"
check "#83 Antigravity Windows Electron Cache excluded" "[ \"\$(status_of \"$W83/Cache\")\" = skipped_excluded ]"
check "#83 Antigravity data dir cache/ not pruned by the Electron Cache exclusion" "[ \"\$(status_of \"$G83/cache/last_conversations.json\")\" = collected ] && [ \"\$(status_of \"$G83/cache\")\" != skipped_excluded ]"

# 2026-10-13 Antigravity Linux round (#83, #90, #91)
check "#90 Antigravity CLI plugin-secrets.json flagged secret" "row \"$H/.config/antigravity/plugin-secrets.json\" | grep -q '\"agent\":\"antigravity\".*\"secret\":true,\"status\":\"collected\"'"
check "#90 Antigravity CLI plugin-secrets.json collected once" "[ \"\$(grep -c 'plugin-secrets.json\"' \"\$M\")\" = 1 ]"
check "#83 Antigravity Electron Dictionaries excluded" "[ \"\$(status_of \"$E83/Dictionaries\")\" = skipped_excluded ] && ! grep -q 'en-US-10-1.bdic\"' \"\$M\""
check "#83 Antigravity app sidecar SDK under lib/node_modules excluded" "[ \"\$(status_of \"$G83/lib/node_modules\")\" = skipped_excluded ] && ! grep -q 'antigravity/lib/node_modules/sidecar_sdk/index.mjs\"' \"\$M\""
check "#83 Antigravity config/node_modules excluded" "[ \"\$(status_of \"$H/.gemini/config/node_modules\")\" = skipped_excluded ] && ! grep -q 'config/node_modules/sidecar_sdk/index.mjs\"' \"\$M\""
check "#91 Antigravity project folderUri discovers project" "[ \"\$(status_of \"$ROOT/srv/agyapp/.antigravityignore\")\" = collected ]"
check "#91 Antigravity drive-letter folderUri discovers project" "[ \"\$(status_of \"$ROOT/srv/agywin/.antigravityignore\")\" = collected ]"
# 2026-10-14 catalog match that is an excluded file (#107)
check "#107 excluded file match gets a skipped_excluded row with its size" "row \"$H/.local/bin/.muse-update.107.exe\" | grep -q '^{\"user\":\"alice\",\"home\":\"$H\",\"agent\":\"muse-code\",\"path\":\"[^\"]*\",\"archive_path\":\"\",\"type\":\"file\",\"size\":5,.*\"sha256\":\"\",\"secret\":false,\"status\":\"skipped_excluded\",\"target\":\"\",\"error\":\"\"}\$'"
check "#107 excluded file match not archived" "! tar -tzf \"\$A\" | grep -q 'muse-update.107.exe'"
# 2026-10-14 Antigravity on Windows (#83)
check "#83 Antigravity Windows staging file collected as antigravity" "row \"$L83/antigravity/staging/s1\" | grep -q '\"agent\":\"antigravity\".*\"status\":\"collected\"'"
check "#83 Antigravity installer and program directory not collected" "! grep -q 'antigravity-updater/installer.exe\"' \"\$M\" && ! grep -q 'Programs/antigravity/Antigravity.exe\"' \"\$M\""
# 2026-10-15 ChatGPT desktop as the OpenAI.Codex package (#113)
check "#113 ChatGPT profile Local Storage collected as chatgpt-desktop" "row \"$C113/Default/Local Storage/leveldb/000003.log\" | grep -q '\"agent\":\"chatgpt-desktop\".*\"secret\":false,\"status\":\"collected\"'"
check "#113 ChatGPT Local State flagged secret" "row \"$C113/Local State\" | grep -q '\"agent\":\"chatgpt-desktop\".*\"secret\":true,\"status\":\"collected\"'"
check "#113 ChatGPT profile and partition cookies flagged secret" "row \"$C113/Default/Network/Cookies\" | grep -q '\"secret\":true,\"status\":\"collected\"' && row \"$X113/Network/Cookies\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "#113 ChatGPT Login Data flagged secret" "row \"$C113/Default/Login Data\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "#113 ChatGPT profile and partition Cache excluded" "[ \"\$(status_of \"$C113/Default/Cache\")\" = skipped_excluded ] && [ \"\$(status_of \"$X113/Cache\")\" = skipped_excluded ] && ! grep -q 'Cache/data_0\"' \"\$M\""
check "#113 ChatGPT component cache beside the profile not in the manifest" "! grep -q 'web/Codex/component_crx_cache' \"\$M\""
check "#113 ChatGPT app log collected as chatgpt-desktop" "row \"$P113/LocalCache/Local/Codex/Logs/2026/10/15/codex-desktop-x.log\" | grep -q '\"agent\":\"chatgpt-desktop\".*\"status\":\"collected\"'"
check "#113 ChatGPT MSIX settings hive collected" "row \"$P113/Settings/settings.dat\" | grep -q '\"agent\":\"chatgpt-desktop\".*\"status\":\"collected\"'"
check "#116 Codex plugin app-server binaries excluded" "[ \"\$(status_of \"$B/.codex/plugins/.plugin-appserver\")\" = skipped_excluded ] && ! grep -q '.plugin-appserver/codex.exe\"' \"\$M\""
check "#115 Codex desktop global state flagged secret" "row \"$B/.codex/.codex-global-state.json\" | grep -q '\"agent\":\"codex-cli\".*\"secret\":true,\"status\":\"collected\"'"
# 2026-10-15 ChatGPT desktop on macOS (#121)
check "#121 ChatGPT macOS Local Storage collected as chatgpt-desktop" "row \"$M121/Default/Local Storage/leveldb/000003.log\" | grep -q '\"agent\":\"chatgpt-desktop\".*\"secret\":false,\"status\":\"collected\"'"
check "#121 ChatGPT macOS profile and partition cookies flagged secret" "row \"$M121/Default/Cookies\" | grep -q '\"secret\":true,\"status\":\"collected\"' && row \"$X121/Cookies\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "#121 ChatGPT macOS Login Data flagged secret" "row \"$M121/Default/Login Data\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "#121 ChatGPT macOS profile and partition Cache excluded" "[ \"\$(status_of \"$M121/Default/Cache\")\" = skipped_excluded ] && [ \"\$(status_of \"$X121/Cache\")\" = skipped_excluded ] && ! grep -q 'Codex/Default/Cache/data_0\"' \"\$M\" && ! grep -q 'codex-browser-app/Cache/data_0\"' \"\$M\""
check "#121 ChatGPT macOS MCP server script excluded, manifest collected" "[ \"\$(status_of \"$M121/executor-plugins/codex-app-tools/server.mjs\")\" = skipped_excluded ] && row \"$M121/executor-plugins/codex-app-tools/.mcp.json\" | grep -q '\"agent\":\"chatgpt-desktop\".*\"status\":\"collected\"'"
check "#121 ChatGPT macOS component cache not in the manifest" "! grep -q 'Application Support/Codex/component_crx_cache' \"\$M\""
check "#121 ChatGPT macOS app log collected as chatgpt-desktop" "row \"$B/Library/Logs/com.openai.codex/2026/10/15/codex-desktop-x.log\" | grep -q '\"agent\":\"chatgpt-desktop\".*\"status\":\"collected\"'"
check "#121 ChatGPT macOS preferences collected" "row \"$B/Library/Preferences/com.openai.codex.plist\" | grep -q '\"agent\":\"chatgpt-desktop\".*\"status\":\"collected\"'"
check "#121 ChatGPT macOS binary cookies flagged secret" "row \"$B/Library/HTTPStorages/com.openai.codex.binarycookies\" | grep -q '\"agent\":\"chatgpt-desktop\".*\"secret\":true,\"status\":\"collected\"'"
check "#121 ChatGPT computer-use group container collected" "row \"$G121/IPC/computeruse.sock.lock\" | grep -q '\"agent\":\"chatgpt-desktop\".*\"status\":\"collected\"'"
check "#121 Codex computer-use app bundle excluded, config collected" "[ \"\$(status_of \"$U121/Codex Computer Use.app\")\" = skipped_excluded ] && ! grep -q 'Computer Use.app/Contents/Info.plist\"' \"\$M\" && row \"$U121/config.json\" | grep -q '\"agent\":\"codex-cli\".*\"status\":\"collected\"'"
# 2026-10-15 special files (#120)
# shellcheck disable=SC2034 # read by the eval'd check strings
N120=$((1 + SOCK120))
check "#120 FIFO recorded as skipped_special, not copied" "row \"$S120/ipc/ipc.fifo\" | grep -q '\"archive_path\":\"\",\"type\":\"fifo\".*\"sha256\":\"\",\"secret\":false,\"status\":\"skipped_special\",\"target\":\"\",\"error\":\"\"'"
if [ "$SOCK120" = 1 ]; then
  check "#120 socket recorded as skipped_special, not copied" "row \"$S120/app-server-daemon/daemon-updater.sock\" | grep -q '\"archive_path\":\"\",\"type\":\"socket\".*\"sha256\":\"\",\"secret\":false,\"status\":\"skipped_special\",\"target\":\"\",\"error\":\"\"'"
fi
check "#120 special files not in the archive" "! tar -tzf \"\$A\" | grep -q 'ipc.fifo\\|daemon-updater.sock'"
check "#120 summary counts skipped_special" "grep -q '\"skipped_special\": $N120,' \"\$S\""
check "#120 stdout skipped line counts special files" "grep -q '^skipped:    [0-9]* excluded, [0-9]* too large, [0-9]* secret, $N120 special\$' \"$OUT/default.stdout\""
check "#120 no symlink row targets its own path" "! grep '\"status\":\"symlink\"' \"\$M\" | sed 's/.*\"path\":\"\([^\"]*\)\".*\"target\":\"\([^\"]*\)\".*/\1|\2/' | grep -q '^\\(.*\\)|\\1\$'"

# 2026-10-16 GitHub Copilot Desktop (#147)
check "#147 Copilot Desktop data.db collected as copilot-desktop" "row \"$D147/data.db\" | grep -q '\"agent\":\"copilot-desktop\".*\"secret\":false,\"status\":\"collected\"' && row \"$D147/data.db-wal\" | grep -q '\"agent\":\"copilot-desktop\".*\"status\":\"collected\"'"
check "#147 Copilot Desktop github-app log collected as copilot-desktop" "row \"$D147/logs/github-app.1.log\" | grep -q '\"agent\":\"copilot-desktop\".*\"status\":\"collected\"'"
check "#147 Copilot Desktop localstorage collected as copilot-desktop" "row \"$L147/localstorage/tauri_localhost_0.localstorage\" | grep -q '\"agent\":\"copilot-desktop\".*\"status\":\"collected\"'"
check "#147 Foundry Local log collected as copilot-desktop" "row \"$ROOT/home/alice/.github-copilot-cli/logs/foundry.core20261016.log\" | grep -q '\"agent\":\"copilot-desktop\".*\"status\":\"collected\"'"
check "#147 Copilot Desktop session workspace.yaml stays copilot-cli" "row \"$D147/session-state/s2/workspace.yaml\" | grep -q '\"agent\":\"copilot-cli\".*\"status\":\"collected\"'"
check "#147 Copilot Desktop ws.token flagged secret" "row \"$D147/run/ws.token\" | grep -q '\"agent\":\"copilot-desktop\".*\"secret\":true,\"status\":\"collected\"'"
check "#147 Copilot Desktop checkpoint ref and HEAD collected as copilot-desktop" "row \"$C147/e0000000-0000-4000-8000-000000000020\" | grep -q '\"agent\":\"copilot-desktop\".*\"status\":\"collected\"' && row \"$R147/HEAD\" | grep -q '\"agent\":\"copilot-desktop\".*\"status\":\"collected\"'"
check "#147 Copilot Desktop repos working tree, worktrees, objects and index excluded" "[ \"\$(status_of \"$D147/repos\")\" = skipped_excluded ] && [ \"\$(status_of \"$R147/objects\")\" = skipped_excluded ] && [ \"\$(status_of \"$R147/index\")\" = skipped_excluded ] && ! grep -q 'repos/proj/README.md\"' \"\$M\" && ! grep -q 'alice-x/AGENTS.md\"' \"\$M\" && ! grep -q 'cdef0123\"' \"\$M\""
check "#147 Copilot Desktop app-skills excluded" "[ \"\$(status_of \"$L147/app-skills\")\" = skipped_excluded ] && ! grep -q 'app-skills/af/SKILL.md\"' \"\$M\""
check "#147 Copilot Desktop chat directory and worktree not projects" "! grep -q 'Project .*/\.copilot/' \"$OUT\"/default/*.log && ! grep -q '\"home\":\"$D147/' \"\$M\" && ! grep -q '\.copilot/chats' \"\$S\" && ! grep -q 'copilot-worktrees' \"\$S\""
check "#147 Copilot Desktop chat directory file collected once as copilot-desktop" "[ \"\$(grep -c 'x-5d404e14/.keep\"' \"\$M\")\" = 1 ] && row \"$D147/chats/2026-10-16/x-5d404e14/.keep\" | grep -q '\"agent\":\"copilot-desktop\"'"
# 2026-10-17 Copilot Desktop Windows round (#147)
check "#147 WebView2 Local Storage collected as copilot-desktop" "row \"$W147/Default/Local Storage/leveldb/000003.log\" | grep -q '\"agent\":\"copilot-desktop\".*\"status\":\"collected\"'"
check "#147 WebView2 cookies and Local State flagged secret" "row \"$W147/Default/Network/Cookies\" | grep -q '\"agent\":\"copilot-desktop\".*\"secret\":true,\"status\":\"collected\"' && row \"$W147/Local State\" | grep -q '\"agent\":\"copilot-desktop\".*\"secret\":true,\"status\":\"collected\"'"
check "#147 WebView2 Cache and component_crx_cache excluded" "[ \"\$(status_of \"$W147/Default/Cache\")\" = skipped_excluded ] && [ \"\$(status_of \"$W147/component_crx_cache\")\" = skipped_excluded ] && ! grep -q 'Cache_Data/x\"' \"\$M\" && ! grep -q 'component_crx_cache/x\"' \"\$M\""
check "#147 Copilot Desktop chat project collected less node_modules" "row \"$P147/package.json\" | grep -q '\"agent\":\"copilot-desktop\".*\"status\":\"collected\"' && [ \"\$(status_of \"$P147/node_modules\")\" = skipped_excluded ] && ! grep -q 'node_modules/m/index.js\"' \"\$M\""
check "#131 Copilot CLI marketplaces excluded" "[ \"\$(status_of \"$K147\")\" = skipped_excluded ] && ! grep -q 'marketplaces/m/.git/HEAD\"' \"\$M\""
check "#147 Copilot pool session cwd not a project" "[ -z \"\$(status_of \"$ROOT/srv/coppool/AGENTS.md\")\" ] && ! grep -q 'coppool' \"\$S\""

# 2026-10-17 session sync round (#153)
SEC153='"secret":true,"status":"collected"'
check "#153 nanobot remote pairing identity and exchange keys flagged secret" "row \"$N153/identity\" | grep -q '\"agent\":\"nanobot\".*$SEC153' && row \"$N153/exchange\" | grep -q '$SEC153' && row \"$N153/request\" | grep -q '\"secret\":false,\"status\":\"collected\"'"
check "#153 Agent Zero plugin config.json flagged secret" "row \"$H/agent-zero/main/usr/$T153\" | grep -q '\"agent\":\"agent-zero\".*$SEC153' && row \"$H/Desktop/agent-zero/usr/$T153\" | grep -q '$SEC153'"
check "#153 Agent Zero volume plugin config.json flagged secret" "row \"$DV/a0_usr/_data/$T153\" | grep -q '\"user\":\"docker\".*$SEC153' && row \"$DV/a0_usr/_data/usr/$T153\" | grep -q '$SEC153'"
check "#153 Cline cached remote config flagged secret" "row \"$G153/remote_config_org1.json\" | grep -q '\"agent\":\"cline\".*$SEC153'"
check "#153 Cline globalStorage cache collected" "row \"$G153/sync-queue.json\" | grep -q '\"agent\":\"cline\".*\"secret\":false,\"status\":\"collected\"' && [ -z \"\$(status_of \"$G153\")\" ]"
check "#153 Cline webhook_config.json flagged secret" "row \"$H/Documents/Cline/webhook_config.json\" | grep -q '\"agent\":\"cline\".*$SEC153'"
check "#153 Gemini CLI bug-memory heap snapshot flagged secret" "row \"$H/.gemini/tmp/gem/bug-memory-1792000000000.heapsnapshot\" | grep -q '\"agent\":\"gemini-cli\".*$SEC153'"
check "#153 little-coder legacy config.json flagged secret" "row \"$H/.little-coder/config.json\" | grep -q '\"agent\":\"little-coder\".*$SEC153'"
check "#153 Qwen Code channel credentials flagged secret" "row \"$H/.qwen/channels/qqbot-credentials.json\" | grep -q '\"agent\":\"qwen-code\".*$SEC153' && row \"$H/.qwen/channels/weixin/account.json\" | grep -q '$SEC153'"
check "#153 Qwen Code channel routing files not flagged" "row \"$H/.qwen/channels/sessions.json\" | grep -q '\"secret\":false,\"status\":\"collected\"' && row \"$H/.qwen/channels/daemon/0123abcd/routes.json\" | grep -q '\"secret\":false,\"status\":\"collected\"'"
check "#153 Kilo log directory collected" "row \"$H/.local/share/kilo/log/2026-10-17T120000.log\" | grep -q '\"agent\":\"kilo-code\".*\"status\":\"collected\"'"
# 2026-10-18 Codex shell snapshots (#160)
check "#160 Codex shell snapshot flagged secret" "row \"$S160\" | grep -q '\"agent\":\"codex-cli\".*$SEC153'"
# 2026-10-19 Codex projectless output directories (#149)
check "#149 Codex projectless output collected" "row \"$W149/outputs/report.md\" | grep -q '\"home\":\"$B\",\"agent\":\"codex-cli\".*\"status\":\"collected\"'"
check "#149 Codex projectless dir not a project" "! grep '^  \"projects\"' \"\$S\" | grep -q 'Documents/Codex' && ! grep -q '\"home\":\"$B/Documents/Codex' \"\$M\" && ! grep -q 'Project .*/Documents/Codex' \"$OUT\"/default/*.log"
check "#149 Codex rollout cwd still a project" "grep '^  \"projects\"' \"\$S\" | grep -qF '\"$B/Documents/app\"'"

# 2026-10-20 Cursor IDE round on macOS (#6)
check "#6 Cursor AgentStores sync index collected" "row \"$C6/AgentStores/cursor_agent_stores/u1/.sync/index.sqlite\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"'"
check "#6 Cursor AgentStores pin collected" "row \"$C6/AgentStores/cursor_agent_stores/.control/u1/pins/1-x.json\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"'"
check "#6 Cursor update-supervisor events collected" "row \"$C6/update-supervisor/33333333-3333-4333-8333-333333333333/events.jsonl\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"'"
check "#6 Cursor update-supervisor binary excluded" "[ \"\$(status_of \"$C6/update-supervisor/33333333-3333-4333-8333-333333333333/cursor-update-supervisor\")\" = skipped_excluded ]"
check "#6 Cursor embedded agent CLI excluded" "[ \"\$(status_of \"$W6/agent-cli\")\" = skipped_excluded ] && ! grep -qF 'agent-cli/.local/share/x' \"\$M\""
check "#6 Cursor agent worker log collected" "row \"$W6/cursor-agent-worker-1.log\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"'"
check "#6 Cursor canvases node_modules excluded" "[ \"\$(status_of \"$B/.cursor/projects/p/canvases/node_modules\")\" = skipped_excluded ] && ! grep -qF 'node_modules/x.d.ts' \"\$M\""
check "#6 Cursor agent transcript collected" "row \"$B/.cursor/projects/p/agent-transcripts/u/u.jsonl\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"'"
check "#6 Cursor statsig cache excluded" "[ \"\$(status_of \"$B/.cursor/statsig-cache.json\")\" = skipped_excluded ]"

# 2026-10-20 Cursor IDE round on Ubuntu (#236)
check "#236 Cursor Linux agent-stores collected" "row \"$L236/u1/.sync/index.sqlite\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"' && row \"$L236/.control/u1/pins/1-x.json\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"'"

# 2026-10-21 Cursor IDE round on Windows (#236)
check "#236 Cursor Windows agent-stores collected" "row \"$S236/u1/.sync/index.sqlite\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"' && row \"$S236/.control/u1/pins/1-x.json\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"'"
check "#236 Cursor Windows embedded agent CLI excluded" "[ \"\$(status_of \"$W236/agent-cli\")\" = skipped_excluded ] && ! grep -qF 'anysphere.cursor-agent-worker/agent-cli/x' \"\$M\""
check "#236 Cursor Windows agent worker log collected" "row \"$W236/cursor-agent-worker-1.log\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"'"
check "#236 Cursor plugin cache excluded" "[ \"\$(status_of \"$P236/cache\")\" = skipped_excluded ] && ! grep -qF 'cache/cursor-public/x/0123abcd/mcp.json' \"\$M\""
check "#236 Cursor local plugins collected" "row \"$P236/local/x.json\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"'"
check "#236 Cursor Windows inno updater excluded" "[ \"\$(status_of \"$U236/inno_updater.exe\")\" = skipped_excluded ]"
check "#236 Cursor Windows update-supervisor state collected" "row \"$U236/app-ready.json\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"' && row \"$U236/state.json\" | grep -q '\"agent\":\"cursor\".*\"status\":\"collected\"'"
# 2026-10-21 OpenHands Agent Canvas credentials and workspaces (#218)
S218='"agent":"openhands".*"secret":true,"status":"collected"'
check "#218 OpenHands Agent Canvas mars-credentials.json flagged secret" "row \"$M218A\" | grep -q '$S218' && row \"$M218B\" | grep -q '$S218' && row \"$M218C\" | grep -q '$S218'"
check "#218 OpenHands automation workspaces excluded" "[ \"\$(status_of \"$H/.openhands/workspaces\")\" = skipped_excluded ] && ! grep -qF '.openhands/workspaces/run1/f' \"\$M\""
check "#218 OpenHands workspaces.json beside the excluded workspaces collected" "[ \"\$(status_of \"$H/.openhands/workspaces.json\")\" = collected ]"

# 2026-10-21 Agent Zero source review (#217)
check "#217 Agent Zero WhatsApp session flagged secret" "row \"$H/agent-zero/main/$W217\" | grep -q '\"agent\":\"agent-zero\".*$SEC153' && row \"$H/Desktop/agent-zero/$W217\" | grep -q '$SEC153' && row \"$DV/a0_usr/_data/$W217\" | grep -q '\"user\":\"docker\".*$SEC153'"
check "#217 Agent Zero ACP workspace and extra folder discovered" "[ \"\$(status_of \"$ROOT/srv/a0acp/AGENTS.md\")\" = collected ] && [ \"\$(status_of \"$ROOT/srv/a0extra/AGENTS.md\")\" = collected ]"
check "#217 Agent Zero connector screen capture collected" "row \"$T217/0000.png\" | grep -q '\"agent\":\"agent-zero\".*\"status\":\"collected\"'"

# 2026-10-21 framework catalog gaps (#223, #224, #225)
check "#223 CrewAI project .crewai collected" "row \"$ROOT/srv/proj/.crewai/last_run.json\" | grep -q '\"home\":\"$ROOT/srv/proj\",\"agent\":\"crewai\".*\"status\":\"collected\"'"
check "#224 difyctl login-pending.yml flagged secret" "row \"$H/.config/difyctl/login-pending.yml\" | grep -q '\"secret\":true,\"status\":\"collected\"' && row \"$H/AppData/Roaming/difyctl/login-pending.yml\" | grep -q '\"secret\":true,\"status\":\"collected\"' && row \"$H/AppData/Local/difyctl/login-pending.yml\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "#225 CLAI 2.0 state directory collected" "row \"$P225/orchestrator.json\" | grep -q '\"agent\":\"pydantic-clai\".*\"status\":\"collected\"' && row \"$P225/workspaces/registry/ws1/workspace.json\" | grep -q '\"agent\":\"pydantic-clai\".*\"status\":\"collected\"' && row \"$P225/workspaces/registry/ws1/session.log\" | grep -q '\"agent\":\"pydantic-clai\".*\"status\":\"collected\"'"
check "#225 CLAI 2.0 workspace token flagged secret" "row \"$P225/workspaces/registry/ws1/token\" | grep -q '\"agent\":\"pydantic-clai\".*\"secret\":true,\"status\":\"collected\"'"
check "#225 CLAI 2.0 workspace clones excluded" "[ \"\$(status_of \"$P225/workspaces/clones\")\" = skipped_excluded ] && ! grep -qF 'repo-0123456789/.git/HEAD' \"\$M\""

# 2026-10-21 Codex worktree cwds and archived threads (#222)
check "#222 Codex archived rollout cwd discovers project" "[ \"\$(status_of \"$ROOT/srv/codexarch/AGENTS.md\")\" = collected ] && grep '^  \"projects\"' \"\$S\" | grep -qF '\"$ROOT/srv/codexarch\"'"
check "#222 Codex worktree cwd not a project" "! grep '^  \"projects\"' \"\$S\" | grep -q '\.codex/worktrees' && [ \"\$(status_of \"$B/.codex/worktrees\")\" = skipped_excluded ] && ! grep -qF 'worktrees/a1b2/repo/AGENTS.md' \"\$M\""
check "#222 Open Interpreter worktree cwd not a project" "! grep '^  \"projects\"' \"\$S\" | grep -q '\.openinterpreter/worktrees' && ! grep -qF 'worktrees/c3d4/repo/AGENTS.md' \"\$M\""

# 2026-10-21 Cody JetBrains plugin files (#214)
check "#214 Cody JetBrains options files collected" "row \"$O214/cody.xml\" | grep -q '\"agent\":\"cody\".*\"secret\":true,\"status\":\"collected\"' && row \"$O214/cody_application_settings.xml\" | grep -q '\"agent\":\"cody\".*\"status\":\"collected\"'"
check "#214 Cody cody_accounts.xml flagged secret" "row \"$O214/cody_accounts.xml\" | grep -q '\"agent\":\"cody\".*\"secret\":true,\"status\":\"collected\"'"
check "#214 Cody cody_accounts_settings.xml not flagged" "row \"$O214/cody_accounts_settings.xml\" | grep -q '\"agent\":\"cody\".*\"secret\":false,\"status\":\"collected\"'"
check "#214 Cody home .sourcegraph collected" "row \"$H/.sourcegraph/cody_settings.json\" | grep -q '\"agent\":\"cody\".*\"secret\":true,\"status\":\"collected\"'"
check "#214 Cody project .idea files collected" "row \"$ROOT/srv/proj/.idea/cody_history.xml\" | grep -q '\"agent\":\"cody\".*\"status\":\"collected\"' && row \"$ROOT/srv/proj/.idea/.sourcegraph/cody_settings.json\" | grep -q '\"agent\":\"cody\".*\"secret\":true,\"status\":\"collected\"'"

# 2026-10-21 agent worktrees inside a project (#216)
check "#216 Gemini CLI and Qwen Code project worktrees excluded" "[ \"\$(status_of \"$G216/.gemini/worktrees\")\" = skipped_excluded ] && [ \"\$(status_of \"$G216/.qwen/worktrees\")\" = skipped_excluded ] && ! grep -qF 'gem/.gemini/worktrees/w1' \"\$M\" && ! grep -qF 'gem/.qwen/worktrees/w1' \"\$M\""
check "#216 Gemini CLI project settings beside the worktrees collected" "row \"$G216/.gemini/settings.json\" | grep -q '\"agent\":\"gemini-cli\".*\"status\":\"collected\"'"

# 2026-10-21 Hermes quick snapshots and desktop connections (#123, #208)
check "#123 Hermes quick snapshot state.db collected" "row \"$Q123/state.db\" | grep -q '\"agent\":\"hermes\".*\"secret\":false,\"status\":\"collected\"' && row \"$Q123/manifest.json\" | grep -q '\"secret\":false,\"status\":\"collected\"' && row \"$W123/state.db\" | grep -q '\"agent\":\"hermes\".*\"secret\":false,\"status\":\"collected\"' && [ -z \"\$(status_of \"$H/.hermes/state-snapshots\")\" ]"
check "#123 Hermes quick snapshot credentials flagged secret" "row \"$Q123/.env\" | grep -q '$SEC153' && row \"$Q123/auth.json\" | grep -q '$SEC153' && row \"$Q123/pairing/telegram-approved.json\" | grep -q '$SEC153'"
check "#208 Hermes desktop connection files flagged secret" "row \"$H/.config/Hermes/connections.json\" | grep -q '\"agent\":\"hermes\".*$SEC153' && row \"$H/.config/Hermes/connection.json\" | grep -q '$SEC153'"

# 2026-10-21 nanobot workspace cron and triggers (#220)
check "#220 nanobot workspace cron jobs and runs collected" "row \"$N220/cron/jobs.json\" | grep -q '\"agent\":\"nanobot\".*\"status\":\"collected\"' && row \"$N220/cron/runs/j1_1_ab.json\" | grep -q '\"agent\":\"nanobot\".*\"status\":\"collected\"'"
check "#220 nanobot workspace triggers and runs collected" "row \"$N220/triggers/triggers.json\" | grep -q '\"agent\":\"nanobot\".*\"status\":\"collected\"' && row \"$N220/triggers/runs/d1.json\" | grep -q '\"agent\":\"nanobot\".*\"status\":\"collected\"'"
check "#220 nanobot trigger queue not collected" "! grep -qF 'nanows/triggers/inbox' \"\$M\""

# 2026-10-21 OpenClaw source review (#219)
check "#219 OpenClaw exec-approvals.json flagged secret" "row \"$O219/exec-approvals.json\" | grep -q '\"agent\":\"openclaw\".*$SEC153'"
check "#219 OpenClaw auth-profile secrets directory flagged secret" "row \"$H/.openclaw-auth-profile-secrets/gateway.env\" | grep -q '\"agent\":\"openclaw\".*$SEC153'"
check "#219 OpenClaw volume exec-approvals.json flagged secret" "row \"$V219/exec-approvals.json\" | grep -q '\"user\":\"docker\".*$SEC153'"
check "#219 OpenClaw Gateway clone excluded" "[ \"\$(status_of \"$O219/projects/$C219\")\" = skipped_excluded ] && ! grep -qF '$C219/repo/README.md' \"\$M\""
check "#219 OpenClaw projects entry that is no clone collected" "row \"$O219/projects/notes/todo.md\" | grep -q '\"agent\":\"openclaw\".*\"status\":\"collected\"'"
check "#219 OpenClaw volume clone, plugin-skills and agent tmp excluded" "[ \"\$(status_of \"$V219/projects/$C219\")\" = skipped_excluded ] && [ \"\$(status_of \"$V219/plugin-skills\")\" = skipped_excluded ] && [ \"\$(status_of \"$V219/agents/main/agent/tmp\")\" = skipped_excluded ] && [ \"\$(status_of \"$V219/agents/main/agent/.tmp\")\" = skipped_excluded ]"
check "#219 volume projects entry that is no clone collected" "row \"$V219/projects/p219/notes.md\" | grep -q '\"user\":\"docker\".*\"status\":\"collected\"'"

# 2026-10-21 OpenCode and Kilo Code source review (#213, #221)
check "#213 OpenCode service.json flagged secret" "row \"$H/.config/opencode/service.json\" | grep -q '\"agent\":\"opencode\".*$SEC153' && row \"$H/.local/state/opencode/service-local.json\" | grep -q '\"agent\":\"opencode\".*$SEC153'"
check "#213 OpenCode desktop data collected" "row \"$D213/drafts.sqlite\" | grep -q '\"agent\":\"opencode\".*\"status\":\"collected\"' && row \"$H/.config/ai.opencode.desktop.beta/drafts.sqlite\" | grep -q '\"agent\":\"opencode\".*\"status\":\"collected\"' && row \"$B/AppData/Roaming/ai.opencode.desktop/drafts.sqlite\" | grep -q '\"agent\":\"opencode\".*\"status\":\"collected\"'"
check "#213 OpenCode desktop compile-cache excluded" "[ \"\$(status_of \"$D213/compile-cache\")\" = skipped_excluded ] && ! grep -qF 'compile-cache/x' \"\$M\""
check "#213 OpenCode Windows temp root collected" "row \"$B/AppData/Local/Temp/opencode/notes.txt\" | grep -q '\"agent\":\"opencode\".*\"status\":\"collected\"'"
check "#221 Kilo sandbox policy and preference collected" "row \"$K221/bb.json\" | grep -q '\"agent\":\"kilo-code\".*\"status\":\"collected\"' && row \"$H/.local/state/kilo-sandbox-preference/bb.json\" | grep -q '\"agent\":\"kilo-code\".*\"status\":\"collected\"'"

# 2026-10-21 Qwen Code session registry (#230)
check "#230 Qwen Code session registry flagged secret" "row \"$H/.qwen/sessions/4242.json\" | grep -q '\"agent\":\"qwen-code\".*\"secret\":true,\"status\":\"collected\"' && row \"$H/.qwen/sessions/4243-0123abcd.json\" | grep -q '\"secret\":true,\"status\":\"collected\"'"

# 2026-10-21 Roo Code CLI cloud credentials (#159)
check "#159 roo cli-credentials.json flagged secret" "row \"$H/.roo/cli-credentials.json\" | grep -q '\"agent\":\"roo-code\".*\"secret\":true,\"status\":\"collected\"'"

# 2026-10-21 Twinny workspace storage (#215)
check "#215 twinny workspaceStorage agent-changes attributed to twinny" "row \"$T215/rjmacarthy.twinny/agent-changes/c1.json\" | grep -q '\"agent\":\"twinny\".*\"status\":\"collected\"'"
check "#215 twinny workspaceStorage neighbour stays vscode" "row \"$T215/workspace.json\" | grep -q '\"agent\":\"vscode\".*\"status\":\"collected\"'"
check "#215 twinny-server forge repos.json flagged secret" "row \"$H/.twinny/server/plugins/github/repos.json\" | grep -q '\"agent\":\"twinny\".*\"secret\":true,\"status\":\"collected\"'"

# 2026-10-21 project git metadata (#253)
# is253 FILE...: each file under the project's .git has a collected row
# with agent project and the project as its home. norow253 PREFIX...: no
# manifest row names a path under the project's .git that starts with it.
# shellcheck disable=SC2317,SC2329 # called from the eval'd check strings
is253() {
  for _g in "$@"; do
    row "$G253/$_g" | grep -q "\"home\":\"$ROOT/srv/proj\",\"agent\":\"project\".*\"status\":\"collected\"" || return 1
  done
}
# shellcheck disable=SC2317,SC2329
norow253() {
  for _g in "$@"; do
    if grep -qF "\"path\":\"$G253/$_g" "$M"; then return 1; fi
  done
}
check "#253 project git HEAD, config, FETCH_HEAD and packed-refs collected as project" "is253 HEAD config FETCH_HEAD packed-refs"
check "#253 project git refs and logs collected as project" "is253 refs/heads/main refs/remotes/origin/main logs/HEAD logs/refs/remotes/origin/main"
check "#253 project git worktrees collected as project" "is253 worktrees/wt1/HEAD worktrees/wt1/gitdir"
check "#253 project git linked worktree index excluded" "[ \"\$(status_of \"$G253/worktrees/wt1/index\")\" = skipped_excluded ]"
check "#253 project git linked worktree submodules excluded" "[ \"\$(status_of \"$G253/worktrees/wt1/modules\")\" = skipped_excluded ] && norow253 worktrees/wt1/modules/sub"
check "#253 project git linked worktree index.lock and sharedindex excluded" "[ \"\$(status_of \"$G253/worktrees/wt1/index.lock\")\" = skipped_excluded ] && [ \"\$(status_of \"$G253/worktrees/wt1/sharedindex.3333333333333333333333333333333333333333\")\" = skipped_excluded ]"
check "#253 project git objects, index, hooks, lfs and modules have no row" "norow253 objects index hooks lfs modules"
check "#253 project git config not flagged secret" "row \"$G253/config\" | grep -q '\"secret\":false,\"status\":\"collected\"'"

# 2026-10-23 claude-code Windows round (#256)
check "#256 Claude Code Windows temp root collected as claude-code" "row \"$T256/scratchpad/notes.txt\" | grep -q '\"agent\":\"claude-code\".*\"secret\":false,\"status\":\"collected\"' && row \"$T256/tasks/b256b256b.output\" | grep -q '\"agent\":\"claude-code\".*\"status\":\"collected\"'"
check "#256 home-level .claude.json.backup flagged secret" "row \"$H/.claude.json.backup\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"'"
check "#256 Claude Code daemon keys and roster flagged secret" "row \"$H/.claude/daemon/control.key\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"' && row \"$H/.claude/daemon/pipe.key\" | grep -q '\"secret\":true,\"status\":\"collected\"' && row \"$H/.claude/daemon/roster.json\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "#256 Claude Code .claude.json backup flagged secret" "row \"$H/.claude/backups/.claude.json.backup.1792800000000\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"'"
check "#256 Claude Code corrupted .claude.json copy flagged secret" "row \"$H/.claude/backups/.claude.json.corrupted.2026-10-23T17-00-00-000Z\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"'"
check "#256 Claude Code paste-cache collected" "row \"$H/.claude/paste-cache/0123456789abcdef.txt\" | grep -q '\"agent\":\"claude-code\".*\"secret\":false,\"status\":\"collected\"'"
check "#256 Claude Code plugin directory cache excluded" "[ \"\$(status_of \"$H/.claude/plugins/plugin-directory-cache-v2.json\")\" = skipped_excluded ]"
check "#256 project git info/exclude collected as project" "is253 info/exclude"

# 2026-10-26 claude-code Linux round (#256)
check "#256 Claude Code version lock collected as claude-code" "row \"$H/.local/state/claude/locks/2.1.310.lock\" | grep -q '\"agent\":\"claude-code\".*\"secret\":false,\"status\":\"collected\"'"
check "#256 Claude Code cache staging collected as claude-code" "row \"$H/.cache/claude/staging/entry\" | grep -q '\"agent\":\"claude-code\".*\"secret\":false,\"status\":\"collected\"'"

# 2026-10-26 claude-code macOS round (#256)
check "#256 Claude Code URL handler bundle collected as claude-code" "row \"$U256/Info.plist\" | grep -q '\"agent\":\"claude-code\".*\"secret\":false,\"status\":\"collected\"' && row \"$U256/MacOS/claude\" | grep -q '\"agent\":\"claude-code\".*\"type\":\"symlink\".*\"status\":\"symlink\",\"target\":\"/home/alice/.local/bin/claude\"'"
check "#256 Claude Code IDE lock and bridge-spawn mcp.json flagged secret" "row \"$H/.claude/ide/53256.lock\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"' && row \"$H/.claude/$S256/mcp.json\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"' && row \"$H/.claude/$S256/append-system-prompt.txt\" | grep -q '\"secret\":false,\"status\":\"collected\"'"
check "#256 relocated claude home IDE lock and bridge-spawn mcp.json flagged secret" "row \"$CCW/ide/53256.lock\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"' && row \"$CCW/$S256/mcp.json\" | grep -q '\"agent\":\"claude-code\".*\"secret\":true,\"status\":\"collected\"'"

# ---- --no-secrets ---------------------------------------------------------
run nosecrets --no-secrets; check "no-secrets exit 0" "[ $? -eq 0 ]"
check "credentials skipped_secret" "[ \"\$(status_of \"$ROOT/home/alice/.claude/.credentials.json\")\" = skipped_secret ]"
check "credentials absent from archive" "! tar -tzf \"\$A\" | grep -q credentials.json"
# 2026-10-11 Claude Desktop Linux deb and Claude Code 2.1.295 session keys (#73, #76)
check "#73 #76 --no-secrets skips link-key and the session key" "[ \"\$(status_of \"$C76/spaces-present/0a0a0a0a/0b0b0b0b/link-key\")\" = skipped_secret ] && [ \"\$(status_of \"$K76\")\" = skipped_secret ]"
# 2026-10-13 Antigravity desktop app (#83, #84)
check "#84 Antigravity plugin token skipped without secrets" "[ \"\$(status_of \"$G83/plugin_data/gdocs/token.json\")\" = skipped_secret ]"
# 2026-10-13 Antigravity Linux round (#83, #90, #91)
check "#90 Antigravity CLI plugin-secrets.json skipped without secrets" "[ \"\$(status_of \"$H/.config/antigravity/plugin-secrets.json\")\" = skipped_secret ]"
# 2026-10-15 ChatGPT desktop as the OpenAI.Codex package (#113)
check "#115 Codex desktop global state skipped without secrets" "[ \"\$(status_of \"$B/.codex/.codex-global-state.json\")\" = skipped_secret ]"
# 2026-10-16 GitHub Copilot Desktop (#147)
check "#147 Copilot Desktop ws.token skipped without secrets" "[ \"\$(status_of \"$D147/run/ws.token\")\" = skipped_secret ]"
# 2026-10-17 session sync round (#153)
check "#153 nanobot remote pairing keys skipped without secrets" "[ \"\$(status_of \"$N153/identity\")\" = skipped_secret ] && [ \"\$(status_of \"$N153/exchange\")\" = skipped_secret ]"
check "#153 Agent Zero plugin config.json skipped without secrets" "[ \"\$(status_of \"$H/agent-zero/main/usr/$T153\")\" = skipped_secret ] && [ \"\$(status_of \"$H/Desktop/agent-zero/usr/$T153\")\" = skipped_secret ]"
check "#153 Agent Zero volume plugin config.json skipped without secrets" "[ \"\$(status_of \"$DV/a0_usr/_data/$T153\")\" = skipped_secret ] && [ \"\$(status_of \"$DV/a0_usr/_data/usr/$T153\")\" = skipped_secret ]"
check "#153 Cline cached remote config skipped without secrets" "[ \"\$(status_of \"$G153/remote_config_org1.json\")\" = skipped_secret ]"
check "#153 Cline webhook_config.json skipped without secrets" "[ \"\$(status_of \"$H/Documents/Cline/webhook_config.json\")\" = skipped_secret ]"
check "#153 Gemini CLI bug-memory heap snapshot skipped without secrets" "[ \"\$(status_of \"$H/.gemini/tmp/gem/bug-memory-1792000000000.heapsnapshot\")\" = skipped_secret ]"
check "#153 little-coder legacy config.json skipped without secrets" "[ \"\$(status_of \"$H/.little-coder/config.json\")\" = skipped_secret ]"
check "#153 Qwen Code channel credentials skipped without secrets" "[ \"\$(status_of \"$H/.qwen/channels/qqbot-credentials.json\")\" = skipped_secret ] && [ \"\$(status_of \"$H/.qwen/channels/weixin/account.json\")\" = skipped_secret ]"
check "#153 Qwen Code channel routing files kept without secrets" "[ \"\$(status_of \"$H/.qwen/channels/sessions.json\")\" = collected ] && [ \"\$(status_of \"$H/.qwen/channels/daemon/0123abcd/routes.json\")\" = collected ]"
# 2026-10-18 Codex shell snapshots (#160)
check "#160 Codex shell snapshot skipped without secrets" "[ \"\$(status_of \"$S160\")\" = skipped_secret ]"
# 2026-10-21 framework catalog gaps (#223, #224, #225)
check "#224 difyctl login-pending.yml skipped without secrets" "[ \"\$(status_of \"$H/.config/difyctl/login-pending.yml\")\" = skipped_secret ]"
check "#225 CLAI 2.0 workspace token skipped without secrets" "[ \"\$(status_of \"$P225/workspaces/registry/ws1/token\")\" = skipped_secret ]"

# 2026-10-21 Agent Zero source review (#217)
check "#217 Agent Zero WhatsApp session skipped without secrets" "[ \"\$(status_of \"$H/agent-zero/main/$W217\")\" = skipped_secret ] && [ \"\$(status_of \"$H/Desktop/agent-zero/$W217\")\" = skipped_secret ] && [ \"\$(status_of \"$DV/a0_usr/_data/$W217\")\" = skipped_secret ]"

# 2026-10-21 Cody JetBrains plugin files (#214)
check "#214 Cody cody_accounts.xml skipped without secrets" "[ \"\$(status_of \"$O214/cody_accounts.xml\")\" = skipped_secret ]"
check "#214 Cody cody.xml skipped without secrets" "[ \"\$(status_of \"$O214/cody.xml\")\" = skipped_secret ]"
check "#214 Cody cody_settings.json skipped without secrets" "[ \"\$(status_of \"$H/.sourcegraph/cody_settings.json\")\" = skipped_secret ] && [ \"\$(status_of \"$ROOT/srv/proj/.idea/.sourcegraph/cody_settings.json\")\" = skipped_secret ]"

# 2026-10-21 Hermes quick snapshots and desktop connections (#123, #208)
check "#123 Hermes quick snapshot credentials skipped without secrets" "[ \"\$(status_of \"$Q123/.env\")\" = skipped_secret ] && [ \"\$(status_of \"$Q123/auth.json\")\" = skipped_secret ] && [ \"\$(status_of \"$Q123/state.db\")\" = collected ]"
check "#208 Hermes desktop connection files skipped without secrets" "[ \"\$(status_of \"$H/.config/Hermes/connections.json\")\" = skipped_secret ]"

# 2026-10-21 OpenClaw source review (#219)
check "#219 OpenClaw credentials skipped without secrets" "[ \"\$(status_of \"$O219/exec-approvals.json\")\" = skipped_secret ] && [ \"\$(status_of \"$H/.openclaw-auth-profile-secrets/gateway.env\")\" = skipped_secret ] && [ \"\$(status_of \"$V219/exec-approvals.json\")\" = skipped_secret ]"

# 2026-10-21 OpenCode and Kilo Code source review (#213, #221)
check "#213 OpenCode service.json skipped without secrets" "[ \"\$(status_of \"$H/.config/opencode/service.json\")\" = skipped_secret ] && [ \"\$(status_of \"$H/.local/state/opencode/service-local.json\")\" = skipped_secret ]"

# 2026-10-21 Qwen Code session registry (#230)
check "#230 Qwen Code session registry skipped without secrets" "[ \"\$(status_of \"$H/.qwen/sessions/4242.json\")\" = skipped_secret ] && [ \"\$(status_of \"$H/.qwen/sessions/4243-0123abcd.json\")\" = skipped_secret ]"

# 2026-10-23 claude-code Windows round (#256)
check "#256 Claude Code daemon keys and .claude.json backup skipped without secrets" "[ \"\$(status_of \"$H/.claude/daemon/control.key\")\" = skipped_secret ] && [ \"\$(status_of \"$H/.claude/daemon/roster.json\")\" = skipped_secret ] && [ \"\$(status_of \"$H/.claude/backups/.claude.json.backup.1792800000000\")\" = skipped_secret ]"
check "#256 relocated claude home session key, daemon key and backup skipped without secrets" "[ \"\$(status_of \"$CCW_K\")\" = skipped_secret ] && [ \"\$(status_of \"$CCW/daemon/control.key\")\" = skipped_secret ] && [ \"\$(status_of \"$CCW/backups/.claude.json.backup.1792800000000\")\" = skipped_secret ]"

# 2026-10-26 claude-code macOS round (#256)
check "#256 Claude Code IDE lock and bridge-spawn mcp.json skipped without secrets" "[ \"\$(status_of \"$H/.claude/ide/53256.lock\")\" = skipped_secret ] && [ \"\$(status_of \"$H/.claude/$S256/mcp.json\")\" = skipped_secret ] && [ \"\$(status_of \"$CCW/ide/53256.lock\")\" = skipped_secret ] && [ \"\$(status_of \"$CCW/$S256/mcp.json\")\" = skipped_secret ]"

# ---- --full ---------------------------------------------------------------
run full --full; check "full exit 0" "[ $? -eq 0 ]"
check "cache contents collected with --full" "[ \"\$(status_of \"$ROOT/home/alice/.claude/cache/junk.bin\")\" = collected ]"
# 2026-10-14 catalog match that is an excluded file (#107)
check "#107 excluded file match collected with --full" "[ \"\$(status_of \"$H/.local/bin/.muse-update.107.exe\")\" = collected ]"

# ---- -u filter ------------------------------------------------------------
run users -u bob; check "users exit 0" "[ $? -eq 0 ]"
check "only bob collected" "! grep -q '\"user\":\"alice\"' \"\$M\" && grep -q '\"user\":\"bob\"' \"\$M\""

# ---- --no-docker ----------------------------------------------------------
run nodocker --no-docker; check "no-docker exit 0" "[ $? -eq 0 ]"
check "no-docker collects no volume" "! grep -q 'docker/volumes' \"\$M\""
check "no-docker recorded in options" "grep -q '\"no_docker\": true' \"\$S\""
check "no-docker prints no docker line" "! grep -q '^docker:' \"$OUT/nodocker.stdout\""

# 2026-10-14 home patterns and the working directory (#105)
(cd "$CWD105" && run cwd105 --no-docker --no-projects); _rc105=$?
M105=$(ls "$OUT/cwd105"/*.manifest.jsonl 2>/dev/null)
S105=$(ls "$OUT/cwd105"/*.collection.json 2>/dev/null)
check "#105 image homes found from a directory with home and Users subdirectories" "[ $_rc105 -eq 0 ] && grep -q '\"user\":\"bob\"' \"$M105\" && [ \"\$(grep '^  \"users\":' \"$S105\")\" = \"\$(grep '^  \"users\":' \"$OUT\"/default/*.collection.json)\" ]"

# 2026-10-14 NESTED_CLAIMS from the environment (#106)
# An inherited value naming a subtree of a matched volume must prune nothing:
# the collector's own claims are internal state, not input. The same in
# smoke.ps1.
NESTED_CLAIMS="$A0/chats"; export NESTED_CLAIMS
run claims106 --no-projects; _rc106=$?
unset NESTED_CLAIMS
check "#106 NESTED_CLAIMS in the environment prunes nothing" "[ $_rc106 -eq 0 ] && [ \"\$(status_of \"$A0/chats/ctx1/chat.json\")\" = collected ]"

# ---- unreadable volume (needs a non-root user; chmod 000 does not stop root)
if [ "$(id -u)" != 0 ]; then
  mkdir -p "$DV/hermes_data/_data/sessions"
  printf '{}\n' >"$DV/hermes_data/_data/sessions/s.json"
  chmod 000 "$DV/hermes_data/_data"
  # a root-only data root, as /var/lib/containers is for a non-root responder
  mkdir -p "$ROOT/var/lib/containers/storage/volumes/x_ollama/_data"
  chmod 000 "$ROOT/var/lib/containers"
  run dockerperm; check "unreadable volume exit 0" "[ $? -eq 0 ]"
  chmod 700 "$DV/hermes_data/_data" "$ROOT/var/lib/containers"
  check "unreadable volume and data root counted in stdout" "grep -q '^docker:     4 volumes found, 2 collected, 2 unreadable (run as root to collect)\$' \"$OUT/dockerperm.stdout\""
  check "unreadable volume noted in collection.json" "grep -q 'docker: volume hermes_data (hermes) at .* is not readable' \"\$S\""
  check "unreadable data root noted in collection.json" "grep -q 'docker: [^\"]*/var/lib/containers is not readable' \"\$S\""
  check "other volumes still collected" "[ \"\$(status_of \"$A0/chats/ctx1/chat.json\")\" = collected ]"
  rm -rf "$DV/hermes_data" "$ROOT/var/lib/containers"
else
  printf 'skip unreadable volume check (running as root)\n'
fi

# ---- Docker Desktop note (macOS layout) -----------------------------------
mkdir -p "$B/Library/Containers/com.docker.docker/Data"
run desktop; check "docker desktop exit 0" "[ $? -eq 0 ]"
check "docker desktop noted in stdout" "grep -q '^docker:     3 volumes found, 2 collected, 0 unreadable; Docker Desktop VM disk not collected\$' \"$OUT/desktop.stdout\""
check "docker desktop noted in collection.json" "grep -q '\"docker: Docker Desktop data at .*com.docker.docker; volumes inside its virtual machine disk are not collected\"' \"\$S\" && grep -q '\"docker_desktop\": true' \"\$S\""
rm -rf "$B/Library/Containers"

# 2026-10-06 frameworks sweep (#64): Dify, Langflow and n8n named volumes, in
# a run of their own so the volume counts above stay as they are. The n8n
# volume holds ~/.n8n, so its config (encryptionKey) is flagged through the
# volume-relative config glob.
FV="$DV/n8n_data/_data"
mkdir -p "$FV/nodes/node_modules/pkg" "$FV/node-definitions" "$FV/n8n-sdk-templates" "$FV/ssh" \
  "$DV/n8n_n8n-data/_data" "$DV/langflow_langflow-data/_data/profile_pictures" \
  "$DV/docker_dify_agent_local_sandbox_home/_data/.local/share/shellctl" "$DV/docker_dify_agent_local_sandbox_workspace/_data"
printf '{"encryptionKey":"k"}\n' >"$FV/config"
printf 'db\n' >"$FV/database.sqlite"
printf 'x\n' >"$FV/nodes/node_modules/pkg/index.js"
printf 'x\n' >"$FV/node-definitions/d.json"
printf 'x\n' >"$FV/n8n-sdk-templates/t.json"
printf 'key\n' >"$FV/ssh/key"
printf 'db\n' >"$DV/n8n_n8n-data/_data/database.sqlite"
printf 'k\n' >"$DV/langflow_langflow-data/_data/secret_key"
printf 'k\n' >"$DV/langflow_langflow-data/_data/cache_secret_key"
printf 'x\n' >"$DV/langflow_langflow-data/_data/profile_pictures/p.svg"
printf 'db\n' >"$DV/docker_dify_agent_local_sandbox_home/_data/.local/share/shellctl/shellctl.db"
printf 'x\n' >"$DV/docker_dify_agent_local_sandbox_workspace/_data/out.txt"
# 2026-10-21 Hermes quick snapshots and desktop connections (#123, #208): a
# Hermes home in a named volume keeps its quick snapshots at the volume root,
# so their credential copies need the volume-relative secret globs.
V123="$DV/hermes_home/_data/state-snapshots/20261001-120004"
mkdir -p "$V123/pairing"
printf 'sqlite\n' >"$V123/state.db"
printf 'KEY=x\n' >"$V123/.env"
printf '{"providers":{}}\n' >"$V123/auth.json"
printf '{}\n' >"$V123/pairing/telegram-approved.json"
run fwvolumes; check "frameworks volumes exit 0" "[ $? -eq 0 ]"
check "n8n_data volume collected as n8n" "row \"$FV/database.sqlite\" | grep -q '\"user\":\"docker\",\"home\":\"$FV\",\"agent\":\"n8n\".*\"status\":\"collected\"'"
check "n8n volume config flagged secret (volume-relative)" "row \"$FV/config\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "n8n volume ssh key flagged secret (volume-relative)" "row \"$FV/ssh/key\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "n8n volume nodes/node_modules excluded (volume-relative)" "[ \"\$(status_of \"$FV/nodes/node_modules\")\" = skipped_excluded ]"
check "n8n volume node-definitions excluded (volume-relative)" "[ \"\$(status_of \"$FV/node-definitions\")\" = skipped_excluded ]"
check "n8n volume n8n-sdk-templates excluded (volume-relative)" "[ \"\$(status_of \"$FV/n8n-sdk-templates\")\" = skipped_excluded ]"
check "n8n_n8n-data volume collected as n8n" "row \"$DV/n8n_n8n-data/_data/database.sqlite\" | grep -q '\"agent\":\"n8n\".*\"status\":\"collected\"'"
check "langflow-data volume secret_key flagged (volume-relative)" "row \"$DV/langflow_langflow-data/_data/secret_key\" | grep -q '\"agent\":\"langflow\".*\"secret\":true,\"status\":\"collected\"'"
check "langflow-data volume cache_secret_key flagged (volume-relative)" "row \"$DV/langflow_langflow-data/_data/cache_secret_key\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "langflow-data volume profile_pictures excluded (volume-relative)" "[ \"\$(status_of \"$DV/langflow_langflow-data/_data/profile_pictures\")\" = skipped_excluded ]"
check "dify sandbox home volume collected as dify" "row \"$DV/docker_dify_agent_local_sandbox_home/_data/.local/share/shellctl/shellctl.db\" | grep -q '\"agent\":\"dify\".*\"status\":\"collected\"'"
check "dify sandbox workspace volume collected as dify" "row \"$DV/docker_dify_agent_local_sandbox_workspace/_data/out.txt\" | grep -q '\"agent\":\"dify\".*\"status\":\"collected\"'"
# 2026-10-21 Hermes quick snapshots and desktop connections (#123, #208)
check "#123 Hermes volume quick snapshot collected, credentials flagged (volume-relative)" "row \"$V123/state.db\" | grep -q '\"user\":\"docker\".*\"agent\":\"hermes\".*\"secret\":false,\"status\":\"collected\"' && row \"$V123/.env\" | grep -q '\"secret\":true,\"status\":\"collected\"' && row \"$V123/auth.json\" | grep -q '\"secret\":true,\"status\":\"collected\"' && row \"$V123/pairing/telegram-approved.json\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
rm -rf "$DV/n8n_data" "$DV/n8n_n8n-data" "$DV/langflow_langflow-data" "$DV/docker_dify_agent_local_sandbox_home" "$DV/docker_dify_agent_local_sandbox_workspace" "$DV/hermes_home"

# ---- --inventory (1.6.0, 2026-10-04) ---------------------------------------
# Stat-only fleet inventory: JSON Lines on stdout, nothing written anywhere.
inv() { # inv NAME ARGS... -> $OUT/NAME.stdout and $OUT/NAME.stderr
  _n=$1; shift
  COLLECTOR_SH="$SHELL_UNDER_TEST" "$SHELL_UNDER_TEST" "$SCRIPT" -r "$ROOT" --inventory "$@" >"$OUT/$_n.stdout" 2>"$OUT/$_n.stderr"
}
# shellcheck disable=SC2317,SC2329 # called from the eval'd check strings
agent_line() { grep -F "\"user\":\"$2\",\"agent\":\"$3\"," "$OUT/$1.stdout" | head -n1; }
INV_HOST_RE='^{"type":"host","host":"[^"]*","collector":"[0-9.]*","mode":"image","at":"[0-9-]*T[0-9:]*Z","users_scanned":[0-9]*,"users_unreadable":[0-9]*,"docker_volumes":[0-9]*}$'
INV_AGENT_RE='^{"type":"agent","host":"[^"]*","user":"[^"]*","agent":"[^"]*","files":[0-9]*,"bytes":[0-9]*,"first":"[^"]*","last":"[^"]*","projects":[0-9]*,"evidence":"[^"]*"}$'
TZ=UTC0 touch -t 202609150102.03 "$ROOT/home/ollama/.ollama/history"
mkdir -p "$OUT/invcwd" "$B/.gemini/antigravity-cli/conversations"
# bob's ~/.gemini holds only the nested antigravity-cli entry: no gemini-cli line.
printf 'db\n' >"$B/.gemini/antigravity-cli/conversations/b1.db"
(cd "$OUT/invcwd" && inv inventory -q); check "inventory exit 0" "[ $? -eq 0 ]"
check "inventory writes nothing in the current directory" "[ -z \"\$(ls -A \"$OUT/invcwd\")\" ]"
check "inventory -q leaves stderr empty" "[ ! -s \"$OUT/inventory.stderr\" ]"
check "inventory first line is the host line, keys in order" "head -n1 \"$OUT/inventory.stdout\" | grep -q '$INV_HOST_RE'"
check "inventory host line counts" "head -n1 \"$OUT/inventory.stdout\" | grep -q '\"users_unreadable\":0,\"docker_volumes\":3}\$'"
check "inventory every later line is an agent line, keys in order" "[ \"\$(sed 1d \"$OUT/inventory.stdout\" | grep -vc '$INV_AGENT_RE')\" = 0 ] && [ \"\$(grep -c . \"$OUT/inventory.stdout\")\" -gt 10 ]"
check "inventory ollama line: history and manifest, excluded blobs not counted" "agent_line inventory ollama ollama | grep -q '\"files\":2,\"bytes\":25,\"first\":\"2026-09-14T00:00:00Z\",\"last\":\"2026-09-15T01:02:03Z\",\"projects\":0,\"evidence\":\".ollama\"}\$'"
check "inventory claude-code evidence in catalog order" "agent_line inventory alice claude-code | grep -q '\"evidence\":\".claude,.claude.json\\*,.claude-\\*/projects,.claude-\\*/history.jsonl,.claude-\\*/.claude.json\\*,.claude-\\*/.credentials.json,.claude-\\*/sessions/\\*.\\*.key,.claude-\\*/daemon/control.key,.claude-\\*/daemon/roster.json,.claude-\\*/backups/.claude.json.\\*,.claude-\\*/ide/\\*.lock,.claude-\\*/bridge-spawn/\\*/mcp.json,.local/state/claude,.cache/claude,Library/Caches/claude-cli-nodejs,AppData/Local/claude-cli-nodejs/Cache/\\*,AppData/Local/Temp/claude,Applications/Claude Code URL Handler.app\"}\$'"
check "inventory first and last set for alice claude-code" "agent_line inventory alice claude-code | grep -q '\"first\":\"20[0-9-]*T[0-9:]*Z\",\"last\":\"20[0-9-]*T[0-9:]*Z\"'"
check "inventory nested entry claimed from the enclosing agent" "agent_line inventory alice antigravity | grep -q '\"evidence\":\"[^\"]*.gemini/antigravity-cli' && agent_line inventory alice gemini-cli | grep -q '\"evidence\":\".gemini\"'"
check "inventory: matched directory with no files of its own gives no line" "[ -z \"\$(agent_line inventory bob gemini-cli)\" ] && agent_line inventory bob antigravity | grep -q '\"files\":1,\"bytes\":3,.*\"evidence\":\".gemini/antigravity-cli\"}\$'"
check "inventory: no agent line has zero files" "! grep -q '\"files\":0,' \"$OUT/inventory.stdout\""
check "inventory projects counted per user" "agent_line inventory alice claude-code | grep -q '\"projects\":[1-9]'"
check "inventory docker volume line" "agent_line inventory docker agent-zero | grep -q '\"files\":7,\"bytes\":127,.*\"projects\":0,\"evidence\":\"\\*a0_usr\"}\$'"
check "inventory rootless docker volume line" "agent_line inventory docker tabby | grep -q '\"files\":1,\"bytes\":23,.*\"evidence\":\"\\*tabby\\*\"}\$'"
check "inventory shared not inventoried" "! grep -q '\"agent\":\"\\(shared\\|project\\|live\\)\"' \"$OUT/inventory.stdout\""
check "inventory prints no path below a home" "! grep -q '$ROOT' \"$OUT/inventory.stdout\""
# 2026-10-19 Codex projectless output directories (#149)
check "#149 inventory codex-cli evidence names Documents/Codex" "agent_line inventory bob codex-cli | grep -q '\"evidence\":\"[^\"]*Documents/Codex'"
if command -v python3 >/dev/null 2>&1; then
  check "inventory stdout is valid JSON Lines" "python3 -c 'import json,sys; [json.loads(l) for l in open(sys.argv[1])]' \"$OUT/inventory.stdout\""
fi
inv inventory-o -o "$OUT/inv-o"; check "inventory with -o exit 0" "[ $? -eq 0 ]"
check "inventory with -o creates no output directory" "[ ! -e \"$OUT/inv-o\" ]"
check "inventory with -o notes it on stderr" "grep -q 'NOTE: --inventory writes nothing; -o .*inv-o ignored' \"$OUT/inventory-o.stderr\""
check "inventory without -q logs to stderr only" "[ -s \"$OUT/inventory-o.stderr\" ] && [ \"\$(grep -vc '$INV_HOST_RE' \"$OUT/inventory-o.stdout\" | head -n1)\" = \"\$(grep -c '$INV_AGENT_RE' \"$OUT/inventory-o.stdout\")\" ]"
inv inventory-full -q --full
check "inventory --full counts excluded files" "agent_line inventory-full ollama ollama | grep -q '\"files\":3,\"bytes\":30,'"
# 2026-10-14 catalog match that is an excluded file (#107)
# --full adds one file for each excl and exclf case of CASES_MUSE, plus the
# updater file, which the default inventory must not count either.
# shellcheck disable=SC2317,SC2329 # called from the eval'd check string
inv_files() { agent_line "$1" alice muse-code | sed 's/.*"files":\([0-9]*\),.*/\1/'; }
check "#107 inventory counts an excluded file match only with --full" "[ \"\$(( \$(inv_files inventory-full) - \$(inv_files inventory) ))\" = \"\$(( \$(printf '%s\\n' \"\$CASES_MUSE\" | grep -c '^excl') + 1 ))\" ]"
inv inventory-u -q -u bob --no-docker
check "inventory -u keeps one user" "! grep -q '\"user\":\"alice\"' \"$OUT/inventory-u.stdout\" && grep -q '\"user\":\"bob\"' \"$OUT/inventory-u.stdout\""
check "inventory --no-docker: no volumes, no docker lines" "head -n1 \"$OUT/inventory-u.stdout\" | grep -q '\"users_scanned\":1,\"users_unreadable\":0,\"docker_volumes\":0}' && ! grep -q '\"user\":\"docker\"' \"$OUT/inventory-u.stdout\""
# 2026-10-04 bug round: #29
if [ "$CASE_INSENSITIVE" = 1 ]; then
  check "#29 inventory evidence keeps only the first spelling" "agent_line inventory alice pearai | grep -q '\"evidence\":\"[^\"]*.config/PearAI/User' && ! agent_line inventory alice pearai | grep -q '.config/pearai/User'"
else
  check "#29 inventory evidence keeps both distinct spellings" "agent_line inventory alice pearai | grep -q '.config/PearAI/User,.config/pearai/User'"
fi
rm -rf "$B/.gemini"
if [ "$(id -u)" != 0 ]; then
  mkdir -p "$ROOT/home/carol/.claude"
  chmod 000 "$ROOT/home/carol"
  inv inventory-perm -q; check "inventory unreadable home exit 0" "[ $? -eq 0 ]"
  chmod 700 "$ROOT/home/carol"
  check "inventory counts the unreadable home" "head -n1 \"$OUT/inventory-perm.stdout\" | grep -q '\"users_unreadable\":1,'"
  check "inventory scanned count includes it" "[ \"\$(head -n1 \"$OUT/inventory-perm.stdout\" | sed 's/.*\"users_scanned\":\\([0-9]*\\).*/\\1/')\" = \"\$(( \$(head -n1 \"$OUT/inventory.stdout\" | sed 's/.*\"users_scanned\":\\([0-9]*\\).*/\\1/') + 1 ))\" ]"
  rm -rf "$ROOT/home/carol"
else
  printf 'skip unreadable home inventory check (running as root)\n'
fi

# ---- live mode without the snapshot (1.6.0) --------------------------------
mkdir -p "$OUT/livehost"
COLLECTOR_SH="$SHELL_UNDER_TEST" "$SHELL_UNDER_TEST" "$SCRIPT" -o "$OUT/livehost" -q -u no-such-user-cac --no-docker --no-projects >/dev/null 2>&1
check "live mode exit 0" "[ $? -eq 0 ]"
LA=$(ls "$OUT/livehost"/*.tar.gz 2>/dev/null)
check "live mode writes no live directory" "! tar -tzf \"$LA\" | grep -q '^./live/'"
check "live mode manifest has no live rows" "! tar -xzOf \"$LA\" ./manifest.jsonl | grep -q '\"agent\":\"live\"'"
check "live mode collection.json has hostname and no no_live" "tar -xzOf \"$LA\" ./collection.json | grep -q '\"hostname\": \"[^\"]' && ! tar -xzOf \"$LA\" ./collection.json | grep -q no_live"
check "--no-live is no longer an option" "! \"$SHELL_UNDER_TEST\" \"$SCRIPT\" --no-live -o \"$OUT/nolive\" -q >/dev/null 2>&1"

# ---- --list ---------------------------------------------------------------
check "--list prints catalog" "\"$SHELL_UNDER_TEST\" \"$SCRIPT\" --list | grep -q '^claude-code|.claude$'"
check "--list prints docker volume table" "\"$SHELL_UNDER_TEST\" \"$SCRIPT\" --list | grep -q '^agent-zero|\\*a0_usr$'"

# 2026-10-04 bug round: #31
# collection.json names the archive and archiver actually used, and records
# the project options. A PATH shim tar that rejects -z forces the tar | gzip
# fallback; a shim gzip that fails as well forces the plain .tar fallback. The
# collector puts the system directories first on PATH, so these runs use a
# copy of it whose PATH line puts the shim directory first. A busybox built
# with the standalone shell (busybox-static, as CI installs) runs its own tar
# and gzip applets before searching PATH, so the shims never run; the probe
# below detects that and skips only the checks that need a forced fallback.
SUMS=$(ls "$OUT/default"/*.collection.json)
check "#31 default summary: archiver tar -z, .tar.gz" "grep -q '\"archiver\": \"tar -z\"' \"$SUMS\" && grep -q '\"archive\": \"[^\"]*\\.tar\\.gz\"' \"$SUMS\""
check "#31 default summary: no_projects false, projects empty" "grep -q '\"no_projects\": false, \"projects\": \\[\\]' \"$SUMS\""
SHIM="$WORK/shim31"; mkdir -p "$SHIM"
REAL_TAR=$(command -v tar)
# shellcheck disable=SC2016 # $1 and $@ belong to the shim, not to this script
printf '#!/bin/sh\ncase "$1" in *z*) echo "tar: -z not supported" >&2; exit 2 ;; esac\nexec "%s" "$@"\n' "$REAL_TAR" >"$SHIM/tar"
chmod +x "$SHIM/tar"
mkdir -p "$WORK/probe31"
printf '#!/bin/sh\necho cac-shim-ran\n' >"$WORK/probe31/tar"
chmod +x "$WORK/probe31/tar"
SHIMS31=no
case $(PATH="$WORK/probe31:$PATH" "$SHELL_UNDER_TEST" -c tar 2>/dev/null) in
  (cac-shim-ran) SHIMS31=yes ;;
esac
[ "$SHIMS31" = yes ] || printf 'skip #31 forced tar | gzip and plain tar fallback checks (the shell runs its own tar applet before PATH)\n'
sed "s|^PATH=\"/usr/bin:|PATH=\"$SHIM:/usr/bin:|" "$SCRIPT" >"$SHIM/collector.sh"
check "#31 shimmed collector copy puts the shim first" "grep -q '^PATH=\"$SHIM:/usr/bin:' \"$SHIM/collector.sh\""
_sc31=$SCRIPT; SCRIPT="$SHIM/collector.sh"
run tgz31 -p "$ROOT/srv/ccwork" -p "$ROOT/srv/cchist"; _rc31=$?
check "#31 tar | gzip fallback exit 0" "[ $_rc31 -eq 0 ] && [ -s \"\$A\" ]"
if [ "$SHIMS31" = yes ]; then
  check "#31 tar | gzip: on-disk summary names tar | gzip" "grep -q '\"archiver\": \"tar | gzip\"' \"\$S\" && grep -q \"\\\"archive\\\": \\\"\${A##*/}\\\"\" \"\$S\""
fi
check "#31 tar | gzip: archived summary matches on-disk" "tar -xzOf \"\$A\" ./collection.json | cmp -s - \"\$S\""
check "#31 -p values recorded in options.projects" "grep -q '\"no_projects\": false, \"projects\": \\[\"$ROOT/srv/ccwork\",\"$ROOT/srv/cchist\"\\]' \"\$S\""
printf '#!/bin/sh\ncat >/dev/null; echo "gzip: broken" >&2; exit 1\n' >"$SHIM/gzip"
chmod +x "$SHIM/gzip"
run tar31 --no-projects; _rc31=$?
SCRIPT=$_sc31
T31=$(ls "$OUT/tar31"/*.tar 2>/dev/null)
if [ "$SHIMS31" = yes ]; then
  check "#31 plain tar fallback exit 0, no .tar.gz left" "[ $_rc31 -eq 0 ] && [ -s \"$T31\" ] && [ -z \"\$A\" ]"
  check "#31 plain tar: on-disk summary names .tar and tar" "grep -q '\"archiver\": \"tar\"' \"\$S\" && grep -q \"\\\"archive\\\": \\\"\${T31##*/}\\\"\" \"\$S\""
  check "#31 plain tar: archived summary matches on-disk" "tar -xOf \"$T31\" ./collection.json | cmp -s - \"\$S\""
  check "#31 plain tar: sidecar names .tar" "grep -q \"  \${T31##*/}\\\$\" \"$T31.sha256\""
fi
check "#31 --no-projects recorded" "grep -q '\"no_projects\": true, \"projects\": \\[\\]' \"\$S\""
if command -v python3 >/dev/null 2>&1; then
  check "#31 fallback summaries are valid JSON" "python3 -c 'import json,sys; [json.load(open(f)) for f in sys.argv[1:]]' \"\$S\" \"$OUT\"/tgz31/*.collection.json"
fi

# 2026-10-05 bug round: #40
# A tar that fails inside tar -cf - | gzip must not leave a truncated .tar.gz
# behind: the collector falls through to the plain .tar. The shim rejects -z,
# writes some bytes and exits 1 for -cf -, and runs the real tar otherwise;
# gzip is the real one. The forced-failure checks reuse the #31 probe.
check "#40 tar | gzip success leaves no tar status file" "! ls -a \"$OUT/tgz31\" | grep -q 'tar-status'"
if [ "$SHIMS31" = yes ]; then
  SHIM40="$WORK/shim40"; mkdir -p "$SHIM40"
  # shellcheck disable=SC2016 # $1, $2 and $@ belong to the shim, not to this script
  printf '#!/bin/sh\ncase "$1" in *z*) echo "tar: -z not supported" >&2; exit 2 ;; esac\nif [ "$1" = -cf ] && [ "$2" = - ]; then printf "partial tar bytes"; echo "tar: forced failure" >&2; exit 1; fi\nexec "%s" "$@"\n' "$REAL_TAR" >"$SHIM40/tar"
  chmod +x "$SHIM40/tar"
  sed "s|^PATH=\"/usr/bin:|PATH=\"$SHIM40:/usr/bin:|" "$_sc31" >"$SHIM40/collector.sh"
  SCRIPT="$SHIM40/collector.sh"
  run tarfail40; _rc40=$?
  SCRIPT=$_sc31
  T40=$(ls "$OUT/tarfail40"/*.tar 2>/dev/null)
  check "#40 tar failure in the pipe: exit 0, plain .tar, no .tar.gz left" "[ $_rc40 -eq 0 ] && [ -s \"$T40\" ] && [ -z \"\$A\" ]"
  check "#40 tar failure in the pipe: summary names .tar and tar" "grep -q '\"archiver\": \"tar\"' \"\$S\" && grep -q \"\\\"archive\\\": \\\"\${T40##*/}\\\"\" \"\$S\""
  check "#40 tar failure in the pipe: archived summary matches on-disk" "tar -xOf \"$T40\" ./collection.json | cmp -s - \"\$S\""
  check "#40 tar failure in the pipe: logged" "grep -q 'tar | gzip: tar exited 1\$' \"$OUT\"/tarfail40/*.log"
  check "#40 tar status file neither left nor archived" "! ls -a \"$OUT/tarfail40\" | grep -q 'tar-status' && ! tar -tf \"$T40\" | grep -q 'tar-status'"
else
  printf 'skip #40 forced tar failure in tar | gzip checks (the shell runs its own tar applet before PATH)\n'
fi

# 2026-10-04 bug round: #32, #38, #39
# A relative -p is resolved against the current directory (image mode too); a
# -p that does not exist gets an error_read row and a log line. The output
# directory check is the existing [ -w ]: a read-only -o exits 2.
mkdir -p "$ROOT/srv/relproj"
printf '# rel\n' >"$ROOT/srv/relproj/AGENTS.md"
_cwd=$(pwd)
cd "$ROOT/srv" || exit 1
run projargs -p relproj -p /nonexistent-cac/proj; _rc=$?
cd "$_cwd" || exit 1
check "-p arguments exit 0" "[ $_rc -eq 0 ]"
check "relative -p resolved against the current directory" "[ \"\$(status_of \"$ROOT/srv/relproj/AGENTS.md\")\" = collected ] && grep -q '\"projects\": \\[.*\"$ROOT/srv/relproj\"' \"\$S\""
check "#31 x #39 options.projects records the resolved -p values" "grep -q '\"no_projects\": false, \"projects\": \\[\"$ROOT/srv/relproj\",\"/nonexistent-cac/proj\"\\]' \"\$S\""
check "missing -p gets one error_read dir row" "[ \"\$(grep -c '\"path\":\"/nonexistent-cac/proj\"' \"\$M\")\" = 1 ] && row /nonexistent-cac/proj | grep -q '\"home\":\"/nonexistent-cac/proj\",\"agent\":\"\",.*\"archive_path\":\"\",\"type\":\"dir\".*\"status\":\"error_read\",\"target\":\"\",\"error\":\"[^\"]*No such file or directory\"'"
check "missing -p logged" "grep -q 'WARNING: project given with -p is not a directory: /nonexistent-cac/proj: ' \"$OUT\"/projargs/*.log"
check "missing -p not listed in projects" "grep -q '^  \"projects\": \\[\"' \"\$S\" && ! grep '^  \"projects\"' \"\$S\" | grep -q nonexistent-cac"
check "missing -p counted as error_read" "grep -q '\"error_read\": 1,' \"\$S\" && grep -q '^errors:     1 (0 error_copy, 1 error_read)\$' \"$OUT/projargs.stdout\""
check "default run has no error_read rows" "grep -q '\"error_read\": 0,' \"$OUT\"/default/*.collection.json && grep -q '^errors:     0 (0 error_copy, 0 error_read)\$' \"$OUT/default.stdout\""
rm -rf "$ROOT/srv/relproj"
if [ "$(id -u)" != 0 ]; then
  mkdir -p "$OUT/readonly"
  chmod 555 "$OUT/readonly"
  COLLECTOR_SH="$SHELL_UNDER_TEST" "$SHELL_UNDER_TEST" "$SCRIPT" -r "$ROOT" -o "$OUT/readonly" -q --no-docker >/dev/null 2>"$OUT/readonly.stderr"
  check "read-only output dir exits 2 before collecting" "[ $? -eq 2 ] && grep -q '^Output dir not writable: ' \"$OUT/readonly.stderr\" && [ -z \"\$(ls -A \"$OUT/readonly\")\" ]"
  chmod 755 "$OUT/readonly"
  # an unreadable home, an unlistable directory and one that cannot be entered
  mkdir -p "$ROOT/home/erin/.claude" "$H/.claude/locked" "$H/.claude/noenter"
  printf 'x\n' >"$H/.claude/locked/f"
  chmod 000 "$ROOT/home/erin" "$H/.claude/locked"
  chmod 600 "$H/.claude/noenter"
  run readperm; _rc=$?
  chmod 700 "$ROOT/home/erin" "$H/.claude/locked" "$H/.claude/noenter"
  check "unreadable paths exit 0" "[ $_rc -eq 0 ]"
  check "unreadable home gets one error_read row" "[ \"\$(grep -c '\"path\":\"$ROOT/home/erin\"' \"\$M\")\" = 1 ] && row \"$ROOT/home/erin\" | grep -q '\"user\":\"erin\",\"home\":\"$ROOT/home/erin\",\"agent\":\"\",.*\"archive_path\":\"\",\"type\":\"dir\",\"size\":0,.*\"status\":\"error_read\",\"target\":\"\",\"error\":\"[^\"]*Permission denied\"'"
  check "unreadable home stays in users, not in users_with_artifacts" "tr -d '\n' <\"\$S\" | grep -q '\"users\": \\[[^]]*\"erin\"' && ! grep '\"users_with_artifacts\"' \"\$S\" | grep -q erin"
  check "unlistable directory in a walk gets an error_read row" "row \"$H/.claude/locked\" | grep -q '\"user\":\"alice\",\"home\":\"$H\",\"agent\":\"claude-code\",.*\"type\":\"dir\",.*\"status\":\"error_read\",.*\"error\":\"[^\"]*Permission denied\"'"
  check "directory that cannot be entered gets an error_read row" "[ \"\$(status_of \"$H/.claude/noenter\")\" = error_read ]"
  check "rest of the home still collected" "[ \"\$(status_of \"$ROOT/home/alice/.claude/projects/-srv-proj/s1.jsonl\")\" = collected ]"
  check "unreadable paths counted" "grep -q '\"error_read\": 3,' \"\$S\" && grep -q '^errors:     3 (0 error_copy, 3 error_read)\$' \"$OUT/readperm.stdout\""
  check "unreadable paths logged" "[ \"\$(grep -c ' read failed: ' \"$OUT\"/readperm/*.log)\" = 3 ]"
  rm -rf "$ROOT/home/erin" "$H/.claude/locked" "$H/.claude/noenter"
else
  printf 'skip unreadable home, directory and output dir checks (running as root)\n'
fi
# 2026-10-14 output directory under a file (#108)
COLLECTOR_SH="$SHELL_UNDER_TEST" "$SHELL_UNDER_TEST" "$SCRIPT" -r "$ROOT" -o "$FILE108/out" -q --no-docker >"$OUT/file108.stdout" 2>"$OUT/file108.stderr"
check "#108 output dir under a file exits 2 with only the create error" "[ $? -eq 2 ] && [ \"\$(cat \"$OUT/file108.stderr\")\" = \"Cannot create output dir: $FILE108/out\" ] && [ ! -s \"$OUT/file108.stdout\" ] && [ -f \"$FILE108\" ]"

# 2026-10-14 exclusion globs and the working directory (#109)
(cd "$WORK/cwd109" && run cwd109 --no-docker --no-projects); _rc109=$?
M109=$(ls "$OUT/cwd109"/*.manifest.jsonl 2>/dev/null)
check "#109 wildcard exclusion holds from a directory with a matching tree" "[ $_rc109 -eq 0 ] && grep -F '\"path\":\"$H/.claude/plugins/y/node_modules\"' \"$M109\" | grep -q '\"status\":\"skipped_excluded\"' && ! grep -q 'node_modules/f.js' \"$M109\""

# 2026-10-14 CDPATH in the environment (#110), sh only: a relative -r with
# CDPATH naming the directory that holds the decoy root, run from the
# directory that holds the image root.
(cd "$WORK" && CDPATH="$WORK/cdp110" COLLECTOR_SH="$SHELL_UNDER_TEST" "$SHELL_UNDER_TEST" "$SCRIPT" -r root -o "$OUT/cdpath110" -q --no-docker --no-projects >"$OUT/cdpath110.stdout" 2>"$OUT/cdpath110.stderr"); _rc110=$?
check "#110 relative -r with CDPATH set collects the image in the working directory" "[ $_rc110 -eq 0 ] && grep -q '^  \"root\": \"$ROOT\",\$' \"$OUT\"/cdpath110/*.collection.json && grep -q '\"user\":\"alice\"' \"$OUT\"/cdpath110/*.manifest.jsonl"

# 2026-10-04 bug round: #29 x #32
# An unreadable catalog match gets one error_read row, and a case variant
# folded into it (case-insensitive filesystem) gets none of its own.
if [ "$(id -u)" != 0 ]; then
  chmod 000 "$H/.config/pearai/User"
  run fold32; _rc=$?
  chmod 755 "$H/.config/pearai/User"
  check "#29 x #32 unreadable case-variant match: exactly one error_read row" "[ $_rc -eq 0 ] && [ \"\$(grep '\"status\":\"error_read\"' \"\$M\" | grep -ciF '/.config/pearai/User\"')\" = 1 ] && grep -q '\"error_read\": 1,' \"\$S\""
  if [ "$CASE_INSENSITIVE" = 1 ]; then
    check "#29 x #32 folded variant has no rows of its own" "! grep -qF '\"path\":\"$H/.config/pearai/User' \"\$M\""
  else
    check "#29 x #32 the readable spelling is still collected" "[ \"\$(status_of \"$H/.config/PearAI/User/case29-upper.json\")\" = collected ]"
  fi
else
  printf 'skip #29 x #32 unreadable case-variant check (running as root)\n'
fi

# 2026-10-07 batched stage worker (#71)
# The stage worker lstats, copies and hashes a chunk of files with one stat,
# one cp per directory and one hasher call. A separate image holds one
# directory with names the hashers escape (newline, backslash, carriage
# return), an unreadable file between readable ones, and 300 files, more than
# one 256-file chunk. CAC_NO_BATCH=1 takes the per-file path; the two
# manifests must match apart from atime, which the first run's reads may move.
# The shasum run uses a copy of the collector whose sha256sum probe looks for
# a name that does not exist, the same sed-copy approach as the #31 shims; a
# PATH shim cannot hide sha256sum, because the collector puts /usr/bin first.
R71="$WORK/root71"; D71="$R71/home/carol/.claude/projects/-srv-p71"; nl71='
'
cr71=$(printf '\r')
mkdir -p "$R71/etc" "$D71" "$R71/home/carol/.claude/file-history/s1"
printf 'carol:x:1002:1002::/home/carol:/bin/sh\n' >"$R71/etc/passwd"
printf 'first\n' >"$D71/a.jsonl"
printf 'newline name\n' >"$D71/nl${nl71}name.jsonl"
printf 'backslash name\n' >"$D71/back\\slash.jsonl"
printf 'cr name\n' >"$D71/cr${cr71}name.jsonl"
printf 'locked\n' >"$D71/m-locked.jsonl"
printf 'last\n' >"$D71/z.jsonl"
_i=0
while [ "$_i" -lt 300 ]; do printf 'v%s\n' "$_i" >"$R71/home/carol/.claude/file-history/s1/f$_i@v1"; _i=$((_i + 1)); done
LOCKED71=no
if [ "$(id -u)" != 0 ]; then chmod 000 "$D71/m-locked.jsonl"; LOCKED71=yes; fi
# shellcheck disable=SC2317,SC2329 # called from the eval'd check strings
hash71() { printf '%b' "$1" | sha256sum | cut -d' ' -f1; }
# shellcheck disable=SC2317,SC2329
sha71() { row "$1" | sed 's/.*"sha256":"\([^"]*\)".*/\1/'; }
# shellcheck disable=SC2317,SC2329
noatime71() { sed 's/"atime":[0-9]*,//' "$1" | sort; }
_root71=$ROOT; ROOT=$R71
run batch71 --no-docker; _rc71=$?; M71=$M
# bsdtar reads a backslash in a member name as an escape, so the backslash
# file is hashed from a full extraction rather than with tar -O (#78).
X71="$WORK/x71"; mkdir -p "$X71"; tar -xzf "$A" -C "$X71" 2>/dev/null
# shellcheck disable=SC2034 # read by the eval'd check expression below
F71="$X71/fs/home/carol/.claude/projects/-srv-p71/back\\slash.jsonl"
check "#71 batched run exit 0, 306 rows" "[ $_rc71 -eq 0 ] && [ \"\$(wc -l <\"\$M\")\" -eq 306 ]"
check "#71 plain name in the batch hashed" "[ \"\$(sha71 \"$D71/a.jsonl\")\" = \"\$(hash71 'first\\n')\" ]"
check "#71 newline name hashed" "[ \"\$(sha71 \"$D71/nl\\\\nname.jsonl\")\" = \"\$(hash71 'newline name\\n')\" ]"
check "#71 newline name: hash matches the archived bytes" "[ \"\$(tar -xzOf \"\$A\" \"./fs/home/carol/.claude/projects/-srv-p71/nl${nl71}name.jsonl\" | sha256sum | cut -d' ' -f1)\" = \"\$(sha71 \"$D71/nl\\\\nname.jsonl\")\" ]"
check "#71 backslash name hashed" "[ \"\$(sha71 \"$D71/back\\\\\\\\slash.jsonl\")\" = \"\$(hash71 'backslash name\\n')\" ]"
check "#71 backslash name: hash matches the archived bytes" "[ \"\$(sha256sum <\"\$F71\" | cut -d' ' -f1)\" = \"\$(sha71 \"$D71/back\\\\\\\\slash.jsonl\")\" ]"
check "#71 carriage return name hashed" "[ \"\$(sha71 \"$D71/cr\\\\rname.jsonl\")\" = \"\$(hash71 'cr name\\n')\" ]"
check "#71 file after the odd names hashed" "[ \"\$(sha71 \"$D71/z.jsonl\")\" = \"\$(hash71 'last\\n')\" ]"
check "#71 files across two chunks all collected and hashed" "[ \"\$(grep -c '/file-history/s1/f[0-9]*@v1\",.*\"sha256\":\"[0-9a-f]\\{64\\}\",\"secret\":false,\"status\":\"collected\"' \"\$M\")\" -eq 300 ] && [ \"\$(sha71 \"$R71/home/carol/.claude/file-history/s1/f299@v1\")\" = \"\$(hash71 'v299\\n')\" ]"
if [ "$LOCKED71" = yes ]; then
  check "#71 unreadable file in the batch: error_copy row with its error" "row \"$D71/m-locked.jsonl\" | grep -q '\"archive_path\":\"\",\"type\":\"file\",\"size\":7,.*\"sha256\":\"\",\"secret\":false,\"status\":\"error_copy\",\"target\":\"\",\"error\":\"[^\"]*Permission denied\"'"
  check "#71 unreadable file in the batch: logged once" "[ \"\$(grep -c 'copy failed: .*/m-locked.jsonl: ' \"$OUT\"/batch71/*.log)\" = 1 ]"
  check "#71 unreadable file in the batch: the rest collected" "[ \"\$(grep -c '\"status\":\"collected\"' \"\$M\")\" -eq 305 ] && ! tar -tzf \"\$A\" | grep -q m-locked"
else
  printf 'skip #71 unreadable file in a batch (running as root)\n'
fi
export CAC_NO_BATCH=1
run nobatch71 --no-docker; _rc71=$?
unset CAC_NO_BATCH
check "#71 per-file run exit 0" "[ $_rc71 -eq 0 ]"
check "#71 batched and per-file manifests match" "noatime71 \"\$M\" >\"$WORK/nb71.txt\" && noatime71 \"$M71\" | cmp -s - \"$WORK/nb71.txt\""
check "#71 batched and per-file manifests in the same order" "sed 's/\"atime\":[0-9]*,//' \"\$M\" >\"$WORK/nb71o.txt\" && sed 's/\"atime\":[0-9]*,//' \"$M71\" | cmp -s - \"$WORK/nb71o.txt\""
if shasum -a 256 /dev/null >/dev/null 2>&1; then
  mkdir -p "$WORK/shasum71"
  sed 's/command -v sha256sum /command -v cac-no-sha256sum /' "$SCRIPT" >"$WORK/shasum71/collector.sh"
  _sc71=$SCRIPT; SCRIPT="$WORK/shasum71/collector.sh"
  run shasum71 --no-docker; _rc71=$?
  SCRIPT=$_sc71
  check "#71 shasum run: exit 0, hash_tool shasum" "[ $_rc71 -eq 0 ] && grep -q '\"hash_tool\": \"shasum\"' \"\$S\""
  check "#71 shasum run: manifest matches the sha256sum run" "noatime71 \"\$M\" | cmp -s - \"$WORK/nb71.txt\""
else
  printf 'skip #71 shasum path (no shasum)\n'
fi
ROOT=$_root71
[ "$LOCKED71" = no ] || chmod 600 "$D71/m-locked.jsonl"

# 2026-10-10 Claude Desktop MSIX build (#73)
# The MSIX build keeps userData in the package's virtualised
# LocalCache/Roaming/Claude, logs in AppData/Local/Claude/logs, and may use
# AppData/Local/Claude-Data/<family>. A separate image holds one Windows
# profile with those trees; the */Claude*/ secret and exclusion globs must
# apply under the new bases, and the Packages secret globs must flag the
# token cache and cookies of both package families.
R73="$WORK/root73"; P73="$R73/Users/bob/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Roaming/Claude"
O73="11111111-1111-4111-8111-111111111111/22222222-2222-4222-8222-222222222222"
Q73="$R73/Users/bob/AppData/Local/Packages/AnthropicPBC.Claude_fnn82j28hfe8t/LocalCache/Roaming/Claude"
L73="$R73/Users/bob/AppData/Local/Claude"; D73="$R73/Users/bob/AppData/Local/Claude-Data/claude_pzs8sxrjxfjjc"
mkdir -p "$P73/claude-code-sessions/$O73" "$P73/local-agent-mode-sessions/$O73/local_33333333-3333-4333-8333-333333333333" \
  "$P73/claude-code/2.1.295/abc" "$P73/Cache" "$P73/Network" "$Q73" "$L73/logs" "$D73"
printf '{"oauth:tokenCache":"enc"}\n' >"$P73/config.json"
printf '{"os_crypt":{}}\n' >"$P73/Local State"
printf '{"mcpServers":{}}\n' >"$P73/claude_desktop_config.json"
printf 'cookies\n' >"$P73/Network/Cookies"
printf '{"sessionId":"local_44444444-4444-4444-8444-444444444444","cwd":"C:\\\\proj"}\n' >"$P73/claude-code-sessions/$O73/local_44444444-4444-4444-8444-444444444444.json"
printf '{"entries":[{"sessionId":"0123456789abcdef0123456789abcdef","folders":[]}]}\n' >"$P73/local-agent-mode-sessions/$O73/remote-session-spaces.json"
printf 'key\n' >"$P73/local-agent-mode-sessions/$O73/local_33333333-3333-4333-8333-333333333333/.audit-key"
printf 'MZ\n' >"$P73/claude-code/2.1.295/abc/claude.exe"
printf 'cache\n' >"$P73/Cache/data_0"
printf '{"oauth:tokenCache":"enc"}\n' >"$Q73/config.json"
printf '[MSIX] Filesystem virtualization active\n' >"$L73/logs/main.log"
printf '{"oauth:tokenCache":"enc"}\n' >"$D73/config.json"
_root73=$ROOT; ROOT=$R73
run store73 --no-docker; _rc73=$?
check "#73 MSIX build run exit 0" "[ $_rc73 -eq 0 ]"
check "#73 Packages Code-tab session record collected as claude-desktop" "row \"$P73/claude-code-sessions/$O73/local_44444444-4444-4444-8444-444444444444.json\" | grep -q '\"agent\":\"claude-desktop\".*\"secret\":false,\"status\":\"collected\"'"
check "#73 Packages session record collected exactly once" "[ \"\$(grep -c 'local_44444444-4444-4444-8444-444444444444.json' \"\$M\")\" = 1 ]"
check "#73 Packages remote-session-spaces.json collected" "row \"$P73/local-agent-mode-sessions/$O73/remote-session-spaces.json\" | grep -q '\"agent\":\"claude-desktop\".*\"secret\":false,\"status\":\"collected\"'"
check "#73 AppData/Local/Claude logs collected as claude-desktop" "row \"$L73/logs/main.log\" | grep -q '\"agent\":\"claude-desktop\".*\"status\":\"collected\"'"
check "#73 Packages config.json flagged secret (Packages/Claude_* glob)" "row \"$P73/config.json\" | grep -q '\"agent\":\"claude-desktop\".*\"secret\":true,\"status\":\"collected\"'"
check "#73 Packages Network/Cookies flagged secret (Packages/Claude_* glob)" "row \"$P73/Network/Cookies\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "#73 AnthropicPBC family config.json flagged secret" "row \"$Q73/config.json\" | grep -q '\"agent\":\"claude-desktop\".*\"secret\":true,\"status\":\"collected\"'"
check "#73 Claude-Data config.json flagged secret (AppData/Local/Claude* glob)" "row \"$D73/config.json\" | grep -q '\"agent\":\"claude-desktop\".*\"secret\":true,\"status\":\"collected\"'"
check "#73 Packages Local State flagged secret (*/Claude*/Local State)" "row \"$P73/Local State\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "#73 Packages claude_desktop_config.json flagged secret (*/Claude*/claude_desktop_config.json)" "row \"$P73/claude_desktop_config.json\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "#73 Packages .audit-key flagged secret (*/Claude*/local-agent-mode-sessions/*/.audit-key)" "row \"$P73/local-agent-mode-sessions/$O73/local_33333333-3333-4333-8333-333333333333/.audit-key\" | grep -q '\"secret\":true,\"status\":\"collected\"'"
check "#73 Packages claude-code excluded (*/Claude*/claude-code)" "[ \"\$(status_of \"$P73/claude-code\")\" = skipped_excluded ] && ! grep -q 'claude.exe' \"\$M\""
check "#73 Packages Cache excluded (*/Claude*/Cache)" "[ \"\$(status_of \"$P73/Cache\")\" = skipped_excluded ] && ! grep -q 'Cache/data_0' \"\$M\""
run nosecrets73 --no-docker --no-secrets; _rc73=$?
check "#73 --no-secrets run exit 0" "[ $_rc73 -eq 0 ]"
check "#73 --no-secrets skips the Packages and Claude-Data token caches" "[ \"\$(status_of \"$P73/config.json\")\" = skipped_secret ] && [ \"\$(status_of \"$Q73/config.json\")\" = skipped_secret ] && [ \"\$(status_of \"$D73/config.json\")\" = skipped_secret ]"
check "#73 --no-secrets skips Local State, claude_desktop_config.json, .audit-key" "[ \"\$(status_of \"$P73/Local State\")\" = skipped_secret ] && [ \"\$(status_of \"$P73/claude_desktop_config.json\")\" = skipped_secret ] && [ \"\$(status_of \"$P73/local-agent-mode-sessions/$O73/local_33333333-3333-4333-8333-333333333333/.audit-key\")\" = skipped_secret ]"
check "#73 --no-secrets still collects the session record" "[ \"\$(status_of \"$P73/claude-code-sessions/$O73/local_44444444-4444-4444-8444-444444444444.json\")\" = collected ]"
run full73 --no-docker --full; _rc73=$?
check "#73 --full run exit 0" "[ $_rc73 -eq 0 ]"
check "#73 --full collects the Packages claude.exe and Cache" "[ \"\$(status_of \"$P73/claude-code/2.1.295/abc/claude.exe\")\" = collected ] && [ \"\$(status_of \"$P73/Cache/data_0\")\" = collected ]"
ROOT=$_root73

if [ "$fail" = 0 ]; then printf 'ALL PASSED (%s)\n' "$SHELL_UNDER_TEST"; rm -rf "$WORK"; else printf 'FAILURES (%s); work dir kept: %s\n' "$SHELL_UNDER_TEST" "$WORK"; fi
exit "$fail"
