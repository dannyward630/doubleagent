# Copyright 2026 Sean Whalen
# SPDX-License-Identifier: Apache-2.0
#
# Smoke test for Collect-AgentArtifacts.ps1: build a fake disk image, run the
# collector in image mode, and check the manifest and archive. Runs under
# Windows PowerShell 5.1 and PowerShell 7 on any OS:
#   powershell.exe -ExecutionPolicy Bypass -File tests\smoke.ps1
#   pwsh -File tests/smoke.ps1
[CmdletBinding()]
param([string]$Collector = '')
Set-StrictMode -Version 2
$ErrorActionPreference = 'Continue'
if ($Collector -eq '') { $Collector = Join-Path (Split-Path -Parent $PSScriptRoot) 'Collect-AgentArtifacts.ps1' }
$Sep = [string][System.IO.Path]::DirectorySeparatorChar
$Work = Join-Path ([System.IO.Path]::GetTempPath()) ("cac-smoke-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
$Root = Join-Path $Work 'root'
$Out = Join-Path $Work 'out'
$script:fail = 0
function Ok([string]$m) { Write-Output "ok   $m" }
function Bad([string]$m) { Write-Output "FAIL $m"; $script:fail = 1 }
function Check([string]$name, [scriptblock]$cond) {
  $res = $false; $why = ''
  try { $res = [bool](& $cond) } catch { $res = $false; $why = " ($($_.Exception.Message))" }
  if ($res) { Ok $name } else { Bad ($name + $why) }
}
function P([string]$rel) { return (Join-Path $Root ($rel.Replace('/', $Sep))) }
# The extended-length form of an absolute Windows path (\\?\C:\... or
# \\?\UNC\server\share\...), which .NET and -LiteralPath open past 260
# characters without LongPathsEnabled (#77); unchanged elsewhere. P stays
# plain because checks compare it with manifest paths; the fixture helpers
# write through XP.
function XP([string]$p) {
  if ($env:OS -ne 'Windows_NT' -or $p.StartsWith('\\?\')) { return $p }
  if ($p.StartsWith('\\')) { return '\\?\UNC\' + $p.Substring(2) }
  if ($p.Length -ge 3 -and $p[1] -eq ':') { return '\\?\' + $p }
  return $p
}
# Every file Mk and MkBig wrote, in extended form, until Test-Made checks
# and clears the list, so a fixture that could not be created is a FAIL.
$script:Made = New-Object System.Collections.ArrayList
function Test-Made {
  $miss = @($script:Made | Where-Object { -not [System.IO.File]::Exists($_) })
  $script:Made.Clear()
  return , $miss
}
function Mk([string]$rel, [string]$content) {
  $p = XP (P $rel)
  [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($p))
  [System.IO.File]::WriteAllText($p, $content, (New-Object System.Text.UTF8Encoding $false))
  [void]$script:Made.Add($p)
}
function MkBig([string]$rel, [int]$bytes) {
  $p = XP (P $rel)
  [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($p))
  $fs = [System.IO.File]::Create($p); $fs.SetLength($bytes); $fs.Close()
  [void]$script:Made.Add($p)
}

Write-Output "== $($PSVersionTable.PSEdition) $($PSVersionTable.PSVersion) on $([Environment]::OSVersion.Platform); work $Work"

# ---- fake image (a Windows profile tree plus a Linux-style home) -----------
Mk 'Users/alice/.claude/projects/-C-proj/s1.jsonl' '{"type":"user","message":{"role":"user","content":"hi"},"timestamp":"2026-10-03T00:00:00Z"}'
Mk 'Users/alice/.claude/history.jsonl' '{"display":"do things","timestamp":1759449600000,"project":"C:\\proj","sessionId":"s1"}'
Mk 'Users/alice/.claude/.credentials.json' '{"claudeAiOauth":{"accessToken":"sk-ant-oat-SECRET"}}'
Mk 'Users/alice/.claude.json' '{"projects":{"C:\\proj":{}}}'
Mk 'Users/alice/.claude/cache/junk.bin' 'cached junk'
Mk 'Users/alice/.claude/weird name with spaces & [brackets].txt' 'weird'
Mk 'proj/CLAUDE.md' '# proj'
Mk 'proj/.claude/settings.local.json' 'settings'
Mk 'Users/alice/.gemini/antigravity-cli/antigravity-oauth-token' 'token'
Mk 'Users/alice/.gemini/antigravity-cli/conversations/c1.db' 'db'
MkBig 'Users/alice/.gemini/antigravity-cli/bin/webm_encoder.exe' 300000
Mk 'Users/alice/.gemini/antigravity-cli/log/cli-1.log' 'log'
Mk 'Users/alice/.gemini/projects.json' '{"projects":{"C:\\gem":"gem"}}'
Mk 'gem/GEMINI.md' '# gem'
Mk 'Users/alice/.codex/sessions/2026/10/03/rollout-1.jsonl' '{"type":"session_meta","payload":{"cwd":"C:\\Users\\alice\\Documents\\app"}}'
Mk 'Users/alice/.codex/auth.json' '{"tokens":{"access_token":"x"}}'
MkBig 'Users/alice/.codex/packages/standalone/releases/1/codex.exe' 200000
Mk 'Users/alice/Documents/app/.cursorrules' 'rules'
Mk 'Users/alice/Documents/app/AGENTS.md' '# agents'
MkBig 'Users/alice/AppData/Roaming/Cursor/User/globalStorage/state.vscdb' 2100000
Mk 'Users/alice/AppData/Roaming/Cursor/User/globalStorage/ms-python.python/x' 'junk'
Mk 'Users/alice/AppData/Roaming/Cursor/User/workspaceStorage/abc/workspace.json' '{"folder":"file:///c%3A/Users/alice/Documents/app"}'
Mk 'Users/alice/AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/state/taskHistory.json' '[{"id":"t1","cwdOnTaskInitialization":"C:\\cl"}]'
Mk 'Users/alice/AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/checkpoints/x' 'ckpt'
Mk 'cl/.clinerules' 'rules'
Mk 'Users/alice/AppData/Roaming/Microsoft/Windows/PowerShell/PSReadLine/ConsoleHost_history.txt' 'Get-Process'
Mk 'Users/alice/AppData/Roaming/Claude/config.json' '{"oauth:tokenCache":"enc"}'
Mk 'Users/alice/AppData/Roaming/Claude/claude_desktop_config.json' '{"mcpServers":{}}'
Mk 'Users/alice/AppData/Roaming/Claude/Cache/index' 'cache'
Mk 'Users/alice/.continue/sessions/sessions.json' '[{"sessionId":"a","workspaceDirectory":"C:\\cont"}]'
Mk 'Users/alice/.continue/index/globalContext.json' '{"mcpOauthStorage":{}}'
Mk 'Users/alice/.continue/index/lancedb/data.lance' 'vec'
Mk 'cont/.continuerc.json' '{}'
Mk 'Users/alice/.local/share/crush/projects.json' '{"projects":[{"path":"C:\\crushproj","data_dir":"C:\\crushproj\\.crush"}]}'
Mk 'crushproj/.crush/crush.db' 'sqlite'
Mk 'Users/alice/.cline/data/settings/providers.json' '{"anthropic":{"apiKey":"sk-x"}}'
Mk 'Users/alice/.env' 'TOKEN=1'
Mk 'Users/Public/Desktop/readme.txt' 'public'
Mk 'Users/Default/NTUSER.DAT' 'default'
Mk 'home/bob/.ollama/models/blobs/sha256-abc' 'blob'
Mk 'home/bob/.ollama/history' 'hist'
# 2026-10-04 a profile with no agent state: listed in users, not counted on stdout
New-Item -ItemType Directory -Path (P 'Users/dave') -Force | Out-Null
Mk 'home/bob/.bash_history' 'export FOO=1'
# v1.3 catalog revision fixtures
Mk 'Users/alice/.factory/cache/session-index/index.db' 'sqlite'
Mk 'Users/alice/.factory/cache/sounds/done.wav' 'ding'
Mk 'Users/alice/.factory/sessions/-C-droid/s1.jsonl' '{"type":"session_start","cwd":"C:\\droid"}'
Mk 'droid/AGENTS.md' '# droid'
Mk 'Users/alice/.kiro/powers/installed/p1/mcp.json' '{"mcpServers":{}}'
Mk 'Users/alice/.kiro/sessions/cli/k1.json' '{"id":"k1","cwd":"C:\\kiroproj"}'
Mk 'kiroproj/.kiroignore' 'steer'
Mk 'Users/alice/.vscode-server/data/User/globalStorage/state.vscdb' 'sqlite'
Mk 'Users/alice/.vscode-server/data/User/globalStorage/saoudrizwan.claude-dev/state/taskHistory.json' '[{"id":"t2","cwdOnTaskInitialization":"C:\\remoteproj"}]'
Mk 'remoteproj/.clinerules' 'rules'
Mk 'Users/alice/.gemini/antigravity-ide/conversations/i1.db' 'db'
Mk 'Users/alice/.gemini/antigravity-cli/history.jsonl' '{"display":"hi","timestamp":1759449600000,"workspace":"C:\\agyproj"}'
Mk 'agyproj/.antigravityignore' 'ignore'
Mk 'Users/alice/.cursor/auth.json' '{"accessToken":"x"}'
Mk 'Users/alice/.copilot/pkg/copilot.exe' 'pkg'
Mk 'Users/alice/.copilot/config.json' '{"token":"x"}'
Mk 'Users/alice/.copilot/session-state/s1/workspace.yaml' "cwd: C:\\copproj`nbranch: main"
Mk 'copproj/AGENTS.md' '# cop'
Mk 'Users/alice/.claude/.device-keys.json' '{"k":"x"}'
Mk 'Users/alice/.local/share/amp/history.jsonl' '{"cwd":"C:\\ampproj","prompt":"hi"}'
Mk 'ampproj/.amp/settings.json' 'amp'
Mk 'kiloproj/.kilo/worktrees/w1/f' 'wt'
Mk 'Users/alice/.cline/data/sessions/s1/s2.json' '{"cwd":"C:\\kiloproj"}'
# 1.4.0 catalog round (2026-10-04): sixteen agents from the October 2026 backlog.
# Same case list as smoke.sh: kind|agent|path relative to alice's profile.
$Cases14 = @'
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
'@
$Cases14 = @($Cases14 -split "`r?`n" | Where-Object { $_ -ne '' })
foreach ($c in $Cases14) {
  $f = @($c -split '\|', 3)
  if ($f[0] -eq 'excl') { Mk "Users/alice/$($f[2])/f" 'x' } else { Mk "Users/alice/$($f[2])" 'x' }
}
Mk 'Users/alice/.hermes/checkpoints/store/projects/0123456789abcdef.json' '{"workdir":"C:\\hermesproj","created_at":1759536000}'
Mk 'hermesproj/.hermes.md' '# hermes'
Mk 'Users/alice/.letta/sessions.jsonl' '{"type":"start","project":"C:\\lettaproj","agentId":"a1"}'
Mk 'lettaproj/.letta/settings.json' '{"hooks":{}}'
Mk 'Users/alice/.letta/lc-local-backend/conversations/c1/messages.jsonl' '{"type":"session","id":"c1","cwd":"C:\\lettaproj2"}'
Mk 'lettaproj2/AGENTS.md' '# letta'
Mk 'Users/alice/.pi/agent/sessions/--C--piproj--/2026-10-04T00-00-00-000Z_u1.jsonl' '{"type":"session","version":3,"id":"u1","cwd":"C:\\piproj"}'
Mk 'piproj/.pi/settings.json' '{}'
Mk 'Users/alice/.pi/agent/2026-10-01T00-00-00-000Z_u2.jsonl' '{"type":"session","version":1,"id":"u2","cwd":"C:\\piproj2"}'
Mk 'piproj2/AGENTS.md' '# pi'
Mk 'Users/alice/.pi/agent/trust.json' '{"C:\\pitrust":true}'
Mk 'pitrust/pi-session-2026-10-04.html' '<html></html>'
Mk 'Users/alice/.pi/agent/crashes.json' '[{"cwd":"C:\\picrash","sessionFile":"x.jsonl"}]'
Mk 'picrash/AGENTS.md' '# pi'
Mk 'Users/alice/.pi/agent/experimental/sessions/s1/meta.json' '{"id":"s1","cwd":"C:\\piexp"}'
Mk 'piexp/AGENTS.md' '# pi'
Mk 'Users/alice/.openinterpreter/sessions/2026/10/04/rollout-2026-10-04T00-00-00-u1.jsonl' '{"type":"session_meta","payload":{"cwd":"C:\\oiproj"}}'
Mk 'oiproj/.openinterpreter/rules/r.md' 'rule'
Mk 'Users/alice/.openinterpreter/archived_sessions/rollout-2026-10-01T00-00-00-u2.jsonl' '{"type":"session_meta","payload":{"cwd":"C:\\oiarch"}}'
Mk 'oiarch/.codewhale/notes.md' 'notes'
Mk 'Users/alice/.openhands/workspaces.json' '{"workspaces":[{"id":"w1","path":"C:\\ohproj"}],"workspaceParents":[]}'
Mk 'ohproj/.openhands/setup.sh' 'echo setup'
Mk 'Users/alice/.openhands/agent-canvas/dev_conversations/a1/meta.json' '{"workspace":{"working_dir":"C:\\ohdev"}}'
Mk 'Users/alice/.openhands/agent-canvas/conversations/a2/meta.json' '{"workspace":{"working_dir":"C:\\ohcanvas"}}'
Mk 'Users/alice/.openhands/conversations/a3/base_state.json' '{"workspace":{"working_dir":"C:\\ohcli"}}'
foreach ($d in @('ohdev', 'ohcanvas', 'ohcli')) { Mk "$d/AGENTS.md" '# oh' }
Mk 'Users/alice/.pearai/sessions/sessions.json' '[{"sessionId":"s1","title":"t","workspaceDirectory":"C:\\pearproj"}]'
Mk 'pearproj/.pearairc.json' '{}'
Mk 'pearproj/.pearai-agent/mcp.json' '{"mcpServers":{}}'
Mk 'Users/alice/.openclaw/openclaw.json' "{`n  // JSON5`n  agents: {`n    defaults: { workspace: 'C:\\clawws' },`n    entries: { main: { agentDir: `"C:\\clawagent`" } },`n  },`n}"
Mk 'Users/alice/.clawdbot/clawdbot.json' '{"agents":{"defaults":{"workspace":"C:\\clawlegacy"}}}'
Mk 'Users/alice/.openclaw-work/openclaw.json' '{agents:{defaults:{workspace:"C:\\clawprofile"}}}'
Mk 'clawws/SOUL.md' '# soul'
Mk 'clawagent/AGENTS.md' '# a'
Mk 'clawlegacy/IDENTITY.md' '# id'
Mk 'clawprofile/MEMORY.md' '# mem'
Mk 'home/bob/.openclaw/openclaw.json' '{}'
Mk 'Users/alice/.nanobot/sessions/0123456789abcdef0123456789abcdef/.workspace' 'C:\nanows'
Mk 'nanows/HEARTBEAT.md' '# hb'
Mk 'Users/alice/.nanobot-work/config.json' '{"agents":{"defaults":{"workspace":"C:\\nanocfg"}}}'
Mk 'nanocfg/memory/MEMORY.md' '# mem'
Mk 'Users/alice/.tabby/config.toml' "[[repositories]]`nname = `"p`"`ngit_url = `"file:///C:/tabbyproj`"`n[[repositories]]`nname = `"u`"`ngit_url = 'file:///srv/tabbyunix'`n"
Mk 'tabbyproj/AGENTS.md' '# tabby'
Mk 'srv/tabbyunix/AGENTS.md' '# tabby'
Mk 'Users/alice/.twinny/embeddings/twinproj/manifest.json' '{"files":{"C:\\twinproj\\src\\a.ts":{"hash":"h1"},"C:\\twinproj\\b.ts":{"hash":"h2"}}}'
Mk 'twinproj/AGENTS.md' '# twin'
# --- 1.5.0 Docker volumes (2026-10-04): a root Docker volume matched to Agent
# Zero, an unmatched volume, and a rootless volume in alice's profile.
Mk 'var/lib/docker/volumes/a0_usr/_data/chats/ctx1/chat.json' '{"id":"ctx1","name":"chat","history":"[]"}'
Mk 'var/lib/docker/volumes/a0_usr/_data/.env' 'API_KEY_OPENAI=sk-x'
Mk 'var/lib/docker/volumes/a0_usr/_data/tmp/playwright/junk' 'junk'
Mk 'var/lib/docker/volumes/pgdata/_data/x' 'pg'
Mk 'var/lib/docker/volumes/metadata.db' 'metadata'
Mk 'Users/alice/.local/share/docker/volumes/tabby_data/_data/events/2026-10-01.json' '{"event":"completion"}'
# --- 2026-10-04 Muse Code: Meta's coding agent CLI. Same case list as smoke.sh,
# relative to alice's profile. The Windows binary is a file exclusion, the Linux
# launcher state is a dot-file glob inside ~/.local/bin, and two discovery
# sources point at projects.
$CasesMuse = @'
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
'@
$CasesMuse = @($CasesMuse -split "`r?`n" | Where-Object { $_ -ne '' })
foreach ($c in $CasesMuse) {
  $f = @($c -split '\|', 3)
  if ($f[0] -eq 'excl') { Mk "Users/alice/$($f[2])/f" 'x' } else { Mk "Users/alice/$($f[2])" 'x' }
}
Mk 'Users/alice/.local/bin/othertool' 'x'
Mk 'Users/alice/.config/muse/trust.json' '{"schema_version":1,"projects":{"C:\\musetrust":{"decision":"trusted"}}}'
Mk 'Users/alice/.local/share/muse/sessions/2026/10/04/01a0f000-0000-7000-8000-000000000001/session.jsonl' '{"schema_version":1,"stream":{"kind":"session","id":"01a0f000-0000-7000-8000-000000000001"},"payload_type":"runtime.session.metadata","payload":{"kind":"metadata","record":{"model_id":"m","workspace_root":"C:\\museproj"}}}'
Mk 'museproj/.muse/hooks.json' '{}'
Mk 'museproj/.muse/worktrees/w1/f' 'x'
Mk 'musetrust/AGENTS.md' '# trusted'

# --- 2026-10-04 relocated Claude Code home: a config home moved with
# CLAUDE_CONFIG_DIR to ~/.claude-work, which keeps .claude.json inside it, and
# claude-code-router's ~/.claude-code-router, which the .claude-* catalog lines
# must not claim. The same files are in smoke.sh.
$CcwS = 'alice/.claude-work/projects/-srv-ccwork/0a0b0c0d-0000-4000-8000-000000000001.jsonl'
Mk "Users/$CcwS" '{"type":"user","cwd":"C:\\ccwork","message":{"role":"user","content":"hi"}}'
Mk 'Users/alice/.claude-work/history.jsonl' '{"display":"hi","project":"C:\\cchist","timestamp":1790848800000}'
Mk 'Users/alice/.claude-work/.claude.json' '{"projects":{"C:\\ccwork":{"allowedTools":[]}}}'
Mk 'Users/alice/.claude-work/.credentials.json' '{"claudeAiOauth":{"accessToken":"sk-ant-oat-SECRET"}}'
# 2026-10-23 (#256): the session key, the daemon files and the .claude.json
# backup of a relocated home are collected by name and flagged secret.
$CcwK = 'Users/alice/.claude-work/sessions/4343.0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef.key'
Mk $CcwK 'session key'
Mk 'Users/alice/.claude-work/daemon/control.key' '0123456789abcdef0123456789abcdef'
Mk 'Users/alice/.claude-work/daemon/roster.json' '{"workers":{}}'
Mk 'Users/alice/.claude-work/backups/.claude.json.backup.1792800000000' "{`"oauthAccount`":{}}`n"
Mk 'Users/alice/.claude-code-router/config.json' '{"PORT":3456}'
Mk 'ccwork/.claude/settings.json' '{}'
Mk 'cchist/.claude/settings.json' '{}'

# 2026-10-04 bug round: #29. Catalog entries that differ only by case:
# .config/PearAI/User before .config/pearai/User, and .config/Cursor/User
# nested under .config/cursor. Distinct directories under pwsh on Linux; one
# directory each on NTFS (Windows PowerShell 5.1) and APFS, where the checks
# expect one row per file. The same files are in smoke.sh.
Mk 'Users/alice/.config/PearAI/User/case29-upper.json' '{}'
Mk 'Users/alice/.config/pearai/User/case29-lower.json' '{}'
Mk 'Users/alice/.config/cursor/case29-cli.json' '{}'
Mk 'Users/alice/.config/Cursor/User/case29-editor.json' '{}'
$caseInsensitive = [System.IO.File]::Exists((P 'Users/alice/.config/pearai/User/case29-upper.json'))

# 2026-10-06 Ollama (#44): the model manifests under .ollama/models/manifests
# are collected while the blobs beside them stay excluded. smoke.sh also
# checks a /usr/share/ollama home listed only in etc/passwd; this collector
# does not read etc/passwd (see docs/coverage.md), so that case is not here.
$olm = 'home/bob/.ollama/models/manifests/registry.ollama.ai/library/llama3.2/latest'
Mk $olm '{"schemaVersion":2}'
[System.IO.File]::SetLastWriteTimeUtc((P $olm), (New-Object DateTime 2026, 9, 14, 0, 0, 0, ([DateTimeKind]::Utc)))
# 2026-10-06 frameworks sweep (#64): agent frameworks, studios and self-hosted
# platforms. Same case list as smoke.sh, relative to alice's profile. CrewAI
# names its run directory after the project folder, so its Linux and macOS
# lines are file-anchored below a mid-path wildcard (.local/share/myproj); the
# Windows line is the class AppData/Local/[Cc]rew[Aa][Ii], tested with CrewAI in
# alice's profile and crewai in bob's home. Apache Camel JBang shares ~/.camel
# with CAMEL, so a JBang status file there must not be collected.
$CasesFw = @'
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
'@
$CasesFw = @($CasesFw -split "`r?`n" | Where-Object { $_ -ne '' })
foreach ($c in $CasesFw) {
  $f = @($c -split '\|', 3)
  if ($f[0] -eq 'excl') { Mk "Users/alice/$($f[2])/f" 'x' } else { Mk "Users/alice/$($f[2])" 'x' }
}
Mk 'Users/alice/.camel/4242-status.json' '{}'
Mk 'Users/alice/.local/share/myproj/unrelated.txt' 'x'
Mk 'home/bob/AppData/Local/crewai/myproj/latest_kickoff_task_outputs.db' 'x'
Mk 'home/bob/AppData/Local/crewai/credentials/tokens.enc' 'x'

$clawLinkOk = $false
try {
  New-Item -ItemType SymbolicLink -Path (P 'home/bob/.clawdbot') -Target '.openclaw' -ErrorAction Stop | Out-Null
  $clawLinkOk = $true
} catch { Write-Output "note: symlink creation not permitted here, .clawdbot symlink check skipped" }
$linkOk = $false
try {
  New-Item -ItemType SymbolicLink -Path (P 'Users/alice/.gemini/antigravity-cli/cli.log') -Target (Join-Path 'log' 'cli-1.log') -ErrorAction Stop | Out-Null
  $linkOk = $true
} catch { Write-Output "note: symlink creation not permitted here, symlink checks skipped" }

# 2026-10-07 (#71): manifest rows are written by hand, not by ConvertTo-Json.
# Names whose JSON needs escaping or that ConvertTo-Json treated specially: a
# quote, a backslash and a tab on POSIX (none is allowed in a Windows name), and
# an apostrophe and an ampersand (Windows PowerShell 5.1's ConvertTo-Json wrote
# them as \u0027 and \u0026). Built with .NET so the backslash stays part of
# the name. Non-ASCII names get their own image after the default run checks.
$Dir71 = [System.IO.Path]::Combine($Root, 'Users', 'alice', '.claude', 'projects', '-C-proj71')
[void][System.IO.Directory]::CreateDirectory($Dir71)
$Names71 = @("amp&apos's.jsonl")
if ($Sep -eq '/') { $Names71 += @('q"uote.jsonl', 'back\slash.jsonl', "tab`there.jsonl") }
foreach ($n71 in $Names71) { [System.IO.File]::WriteAllText([System.IO.Path]::Combine($Dir71, $n71), '{"type":"user"}', (New-Object System.Text.UTF8Encoding $false)) }

# 2026-10-10 long paths (#77): a transcript more than 260 characters below
# the image root wherever the work dir is (five 40-character directory
# names), so the collector must enumerate, copy and hash it, and stage it at
# a longer path still, without LongPathsEnabled on Windows.
$Deep77 = 'Users/alice/.claude/projects/-C-deep77/' + ((1..5 | ForEach-Object { 'd' + $_ + ('x' * 38) }) -join '/') + '/deep.jsonl'
$Body77 = '{"type":"user","message":{"role":"user","content":"deep"},"timestamp":"2026-10-10T00:00:00Z"}'
$Sha77 = ([BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash((New-Object System.Text.UTF8Encoding $false).GetBytes($Body77))) -replace '-', '').ToLower()
Mk $Deep77 $Body77

# 2026-10-11 Claude Desktop Linux deb and Claude Code 2.1.295 session keys (#73, #76)
# The layout observed under ~/.config/Claude from the Linux .deb: logs inside
# the data directory, the space-link signing key under
# spaces-present/<acct 8 hex>/<org 8 hex>/, the CLI temp-root list in
# git-shadow/, a Code-tab record, and the downloaded CLI under claude-code/,
# which stays excluded. Beside them, Claude Code's per-process session key
# next to its sessions/<pid>.json. Checks follow the default and NoSecrets
# runs below; the same files are in smoke.sh.
$c76 = 'Users/alice/.config/Claude'
$o76 = '0a0a0a0a-0000-4000-8000-00000000000a/0b0b0b0b-0000-4000-8000-00000000000b'
$x76 = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'
$k76 = "Users/alice/.claude/sessions/4242.$x76.key"
$l76 = "$c76/spaces-present/0a0a0a0a/0b0b0b0b/link-key"
$s76 = "$c76/claude-code-sessions/$o76/local_76767676-7676-4676-8676-767676767676.json"
Mk $l76 'link-key ciphertext'
Mk "$c76/git-shadow/cli-temp-roots.json" '["/tmp/claude-1000"]'
Mk "$c76/logs/main.log" '2026-10-11 10:00:00 [info] [CCD] Installed'
Mk "$c76/claude-code/2.1.295/9b32b47ec4b3/claude" 'ELF'
Mk "$c76/claude-code/2.1.295/9b32b47ec4b3/.payload" ('{"sha256":"' + $x76 + '","size":4}')
Mk "$c76/claude-code/2.1.295/9b32b47ec4b3/.verified" $x76
Mk $s76 '{"sessionId":"local_76767676-7676-4676-8676-767676767676","cliSessionId":"76767676-0000-4000-8000-000000000076","cwd":"/srv/proj","originCwd":"/srv/proj"}'
Mk 'Users/alice/.claude/sessions/4242.json' '{"pid":4242,"sessionId":"76767676-0000-4000-8000-000000000076","entrypoint":"claude-desktop","kind":"interactive"}'
Mk $k76 'session key'

# 2026-10-11 Claude Code CLI cache directory (#81)
# The CLI's env-paths cache directory, observed on macOS under
# ~/Library/Caches/claude-cli-nodejs: per-project MCP server logs,
# <cwd slug>/mcp-logs-<server>/<timestamp>.jsonl, one {cwd, debug,
# sessionId, timestamp} object per line. Collected as claude-code, not
# secret. Checks follow the default run below; the same file is in smoke.sh.
$f81 = 'Users/alice/Library/Caches/claude-cli-nodejs/-home-alice-proj/mcp-logs-terminal/2026-10-12T02-23-51-709Z.jsonl'
Mk $f81 '{"cwd":"/home/alice/proj","debug":"MCP server \"terminal\": connected","sessionId":"81818181-0000-4000-8000-000000000081","timestamp":"2026-10-12T02:23:51.709Z"}'
# The Windows layout puts the slug directories under Cache/, which the
# catalog names as Cache/* so the PowerShell exclusion */Claude*/Cache,
# matched without case, does not prune it.
$w81 = 'Users/alice/AppData/Local/claude-cli-nodejs/Cache/C--Users-alice-proj/mcp-logs-ccd-host/2026-10-12T02-23-51-709Z.jsonl'
Mk $w81 '{"cwd":"C:\\Users\\alice\\proj","debug":"MCP server \"ccd-host\": connected","sessionId":"81818181-0000-4000-8000-000000000081","timestamp":"2026-10-12T02:23:51.709Z"}'
# 2026-10-13 Antigravity desktop app (#83, #84)
# The layout observed on macOS from the desktop app 2.23.0: its data
# directory ~/.gemini/antigravity with a conversation database, a crash log,
# a plugin's OAuth token and binary under plugin_data/, the binaries in bin/,
# and the plugin marketplace cache beside a cache file the app shares with
# the CLI; then the Electron user-data directory with its Cache and Code
# Cache, the macOS logs directory, and the Windows form of the user-data
# directory. Cache under the Electron directory is excluded by its three
# explicit bases, never by */Antigravity/Cache, which this collector's
# case-insensitive match would also apply to .gemini/antigravity/cache.
# Checks follow the default and NoSecrets runs below; the same files are in
# smoke.sh.
$g83 = 'Users/alice/.gemini/antigravity'
$e83 = 'Users/alice/Library/Application Support/Antigravity'
$w83 = 'Users/alice/AppData/Roaming/Antigravity'
Mk "$g83/conversations/a1.db" 'sqlite'
Mk "$g83/crashes/crash_1.log" 'crash'
Mk "$g83/plugin_data/gdocs/token.json" '{"token":{"access_token":"x","refresh_token":"y"}}'
Mk "$g83/plugin_data/gdocs/bin/gdocs-1" 'bin'
Mk "$g83/bin/webm_encoder" 'bin'
Mk "$g83/cache/marketplaces/official/marketplace.json" '{"name":"official","plugins":[]}'
Mk "$g83/cache/last_conversations.json" '{"x":"a1"}'
Mk "$e83/app_storage.json" '{"lastCreatedProjectId":"p1"}'
Mk "$e83/Cache/data_0" 'cache'
Mk "$e83/Code Cache/js/x" 'js'
Mk 'Users/alice/Library/Logs/Antigravity/main.log' '[2026-10-13 18:28:00.000] [info]  Starting app (v2.23.0)'
Mk "$w83/app_storage.json" '{"lastCreatedProjectId":"p1"}'
Mk "$w83/Cache/data_0" 'cache'
# 2026-10-13 Antigravity Linux round (#83, #90, #91)
# From the Ubuntu install of CLI 1.3.4 and the desktop app 2.23.1, in the
# Windows layout: the CLI's file secret store plugin-secrets.json, here in
# the app's AppData/Roaming/Antigravity because the directory is shared on
# a case-insensitive filesystem (secret, collected once), the spell-check
# Dictionaries directory of the Electron user-data directory and the
# sidecar SDK the app installs twice, under .gemini/antigravity/lib/node_modules
# and .gemini/config/node_modules (excluded), and two app project files:
# one pretty-printed as observed, with two spaces between the colon and the
# file:/// folderUri, and one with a percent-encoded drive letter. Both
# projects must be discovered (#91). Checks follow the default and
# NoSecrets runs below; the same files, in the Linux layout, are in smoke.sh.
Mk "$w83/plugin-secrets.json" '{"gdocs":"x"}'
Mk "$w83/Dictionaries/en-US-10-1.bdic" 'bdic'
Mk "$g83/lib/node_modules/sidecar_sdk/index.mjs" 'export {}'
Mk 'Users/alice/.gemini/config/node_modules/sidecar_sdk/index.mjs' 'export {}'
Mk 'Users/alice/.gemini/config/projects/91919191-0000-4000-8000-000000000091.json' (@('{', '  "id": "91919191-0000-4000-8000-000000000091",', '  "projectResources": {', '    "resources": [', '      {', '        "folderUri":  "file:///C:/agyapp"', '      }', '    ]', '  }', '}', '') -join "`n")
Mk 'Users/alice/.gemini/config/projects/91919191-0000-4000-8000-000000000092.json' (@('{', '  "id": "91919191-0000-4000-8000-000000000092",', '  "projectResources": {', '    "resources": [', '      {', '        "folderUri":  "file:///c%3A/agywin"', '      }', '    ]', '  }', '}', '') -join "`n")
Mk 'agyapp/.antigravityignore' 'ignore'
Mk 'agywin/.antigravityignore' 'ignore'
# 2026-10-14 home patterns and the working directory (#105)
# A directory outside the image with home and Users subdirectories, the
# working directory of the cwd105 run below: the image's homes must still
# be found, bob's among them. The same in smoke.sh, where the sh collector
# once expanded its home patterns here.
$cwd105 = Join-Path $Work 'cwd105'
New-Item -ItemType Directory -Path (Join-Path (Join-Path $cwd105 'home') 'analyst') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path (Join-Path $cwd105 'Users') 'analyst') -Force | Out-Null
# 2026-10-14 catalog match that is an excluded file (#107)
# Muse Code's staged updater as a file, matched by the catalog line
# .local/bin/.muse-* and by the exclusion .local/bin/.muse-update.*: one
# skipped_excluded row with its size, as for a file a walk prunes; collected
# with -Full; counted by the inventory only with -Full. The same file is in
# smoke.sh.
Mk 'Users/alice/.local/bin/.muse-update.107.exe' "1070`n"
# 2026-10-14 output directory under a file (#108)
# A plain file outside the image: the check after the read-only output
# directory check below gives -OutputDir a path under it. The same in
# smoke.sh.
$file108 = Join-Path $Work 'file108'
[System.IO.File]::WriteAllText($file108, "x`n")
# 2026-10-14 exclusion globs and the working directory (#109)
# A plugin node_modules in alice's profile, excluded by the wildcard glob
# .claude/plugins/*/node_modules, and a directory outside the image holding
# another tree that the glob matches, the working directory of the cwd109
# run below. The same in smoke.sh, where the sh collector once expanded the
# glob against that directory.
Mk 'Users/alice/.claude/plugins/y/node_modules/f.js' "module.exports = 1`n"
$cwd109 = Join-Path $Work 'cwd109'
New-Item -ItemType Directory -Path (Join-Path $cwd109 '.claude/plugins/x/node_modules') -Force | Out-Null
# 2026-10-14 Antigravity on Windows (#83)
# From the Windows 11 install of the desktop app 2.23.1 and CLI 1.3.5: the
# marketplace staging directory under AppData/Local/antigravity (the Windows
# form of .cache/antigravity, empty on the install, given a file here so
# it has a row), beside the installer's AppData/Local/antigravity-updater
# and the app's program directory AppData/Local/Programs/antigravity, which
# the catalog line must not match. Checks follow the default run below; the
# same files are in smoke.sh.
$l83 = 'Users/alice/AppData/Local'
Mk "$l83/antigravity/staging/s1" "staged`n"
Mk "$l83/antigravity-updater/installer.exe" "exe`n"
Mk "$l83/Programs/antigravity/Antigravity.exe" "exe`n"

# 2026-10-15 ChatGPT desktop as the OpenAI.Codex package (#113)
# From the Windows 11 install of ChatGPT 26.1007.9446.0: the Chromium
# profile under the package's web/Codex user-data directory, with a
# storage partition, the app log and the MSIX settings hive. The component
# cache beside the profile is not a catalog line and must get no row. The
# bundled Codex's copied binaries and global state go in alice's .codex
# (#115, #116). Checks follow the default and -NoSecrets runs below; the
# same files are in smoke.sh, the .codex ones under bob.
$p113 = 'Users/alice/AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0'
$c113 = "$p113/LocalCache/Roaming/Codex/web/Codex"
$x113 = "$c113/Default/Partitions/codex-browser-app"
Mk "$c113/Default/Local Storage/leveldb/000003.log" "ldb`n"
Mk "$c113/Local State" "{`"os_crypt`":{}}`n"
Mk "$c113/Default/Network/Cookies" "cookies`n"
Mk "$x113/Network/Cookies" "cookies`n"
Mk "$c113/Default/Login Data" "logins`n"
Mk "$c113/Default/Cache/data_0" "cache`n"
Mk "$x113/Cache/data_0" "cache`n"
Mk "$c113/component_crx_cache/metadata.json" "{}`n"
Mk "$p113/LocalCache/Local/Codex/Logs/2026/10/15/codex-desktop-x.log" "log`n"
Mk "$p113/Settings/settings.dat" "hive`n"
Mk 'Users/alice/.codex/plugins/.plugin-appserver/codex.exe' "exe`n"
Mk 'Users/alice/.codex/.codex-global-state.json' "{}`n"

# 2026-10-15 ChatGPT desktop on macOS (#121)
# From the macOS 26.6.2 install of ChatGPT 26.1007.71326 (bundle id
# com.openai.codex): the Chromium profile under Application Support/Codex
# (its cookie store directly in the profile), the bundled MCP server's
# script beside its manifest, the app log, preferences, URL-session
# cookies and the computer-use group container, and the computer-use app
# bundle the app copies into .codex. The component cache beside the
# profile gets no row. Checks follow the default run below; the same
# files are in smoke.sh under bob.
$m121 = 'Users/alice/Library/Application Support/Codex'
$x121 = "$m121/Default/Partitions/codex-browser-app"
$g121 = 'Users/alice/Library/Group Containers/2DC432GLL2.com.openai.sky.CUAService'
$u121 = 'Users/alice/.codex/computer-use'
Mk "$m121/Default/Local Storage/leveldb/000003.log" "ldb`n"
Mk "$m121/Default/Cookies" "cookies`n"
Mk "$x121/Cookies" "cookies`n"
Mk "$m121/Default/Login Data" "logins`n"
Mk "$m121/Default/Cache/data_0" "cache`n"
Mk "$x121/Cache/data_0" "cache`n"
Mk "$m121/executor-plugins/codex-app-tools/server.mjs" "js`n"
Mk "$m121/executor-plugins/codex-app-tools/.mcp.json" "{}`n"
Mk "$m121/component_crx_cache/metadata.json" "{}`n"
Mk 'Users/alice/Library/Logs/com.openai.codex/2026/10/15/codex-desktop-x.log' "log`n"
Mk 'Users/alice/Library/Preferences/com.openai.codex.plist' "plist`n"
Mk 'Users/alice/Library/HTTPStorages/com.openai.codex.binarycookies' "cookies`n"
Mk "$g121/IPC/computeruse.sock.lock" ''
Mk "$u121/Codex Computer Use.app/Contents/Info.plist" "plist`n"
Mk "$u121/config.json" "{}`n"

# 2026-10-16 GitHub Copilot Desktop (#147)
# From the Ubuntu 26.04 arm64 install of GitHub Copilot Desktop 1.1.29: the
# app shares .copilot with the CLI. Its store, run files, chat and repository
# directories and log are nested copilot-desktop entries; its sessions stay
# copilot-cli. A session cwd under .copilot (a chat directory, a worktree) is
# not a project. The data directory and Foundry Local's directory are its own
# entries. A clone's .git is collected (its checkpoint refs), less objects and
# index; the clones' working trees and the worktrees stay excluded with repos.
# entries. Checks follow the default and -NoSecrets runs below; the same
# files are in smoke.sh under alice.
$d147 = 'Users/alice/.copilot'
$l147 = 'Users/alice/.local/share/com.github.githubapp'
Mk "$d147/data.db" "sqlite`n"
Mk "$d147/data.db-wal" "wal`n"
Mk "$d147/run/ws.token" ('A' * 49 + "`n")
Mk "$d147/run/ws.port" "12345`n"
Mk "$d147/chats/2026-10-16/x-5d404e14/.keep" ''
Mk "$d147/repos/proj/README.md" "# proj`n"
$r147 = "$d147/repos/proj/.git"
$c147 = "$r147/refs/copilot/checkpoints/5e55a0a1-0000-4000-8000-000000000001/00000000000000000001"
Mk "$r147/HEAD" "ref: refs/heads/main`n"
Mk "$c147/e0000000-0000-4000-8000-000000000020" "0123456789abcdef0123456789abcdef01234567`n"
Mk "$r147/objects/ab/cdef0123" "object`n"
Mk "$r147/index" "index`n"
Mk "$d147/repos/copilot-worktrees/proj/alice-x/AGENTS.md" "# wt`n"
Mk "$d147/logs/github-app.1.log" "log`n"
$cwd147 = 'C:\Users\alice\.copilot\chats\2026-10-16\x-5d404e14'
Mk "$d147/session-state/s2/workspace.yaml" "cwd: $cwd147`nclient_name: github/autopilot`n"
$wt147 = 'C:\Users\alice\.copilot\repos\copilot-worktrees\proj\alice-x'
Mk "$d147/session-state/s3/workspace.yaml" "cwd: $wt147`nclient_name: github/autopilot`n"
Mk "$l147/localstorage/tauri_localhost_0.localstorage" "sqlite`n"
Mk "$l147/app-skills/af/SKILL.md" "# af`n"
Mk 'Users/alice/.github-copilot-cli/logs/foundry.core20261016.log' "log`n"

# 2026-10-17 Copilot Desktop Windows round (#147)
# From the Windows 11 arm64 install of GitHub Copilot Desktop 1.1.30: the
# WebView2 user data folder (AppData/Local/com.github.githubapp) is a
# copilot-desktop entry less its Chromium caches; a project the agent built in
# a chat directory keeps its files but not its node_modules; the Copilot CLI's
# marketplace clone is excluded (#131). A session directory with no
# events.jsonl is a pool or probe session the app never prompted, and its cwd
# (the install directory on Windows) is not a project; s1, s2 and s3 get an
# events.jsonl so the discovery and .copilot rules above stay tested. Checks
# follow the default run below; the same files are in smoke.sh under alice.
$w147 = 'Users/alice/AppData/Local/com.github.githubapp/EBWebView'
$p147 = "$d147/chats/2026-10-17/x-90825c78/proj"
$k147 = 'Users/alice/AppData/Local/copilot/marketplaces'
Mk "$w147/Default/Local Storage/leveldb/000003.log" "leveldb`n"
Mk "$w147/Default/Network/Cookies" "cookies`n"
Mk "$w147/Local State" "{`"os_crypt`":{}}`n"
Mk "$w147/Default/Cache/Cache_Data/x" "cache`n"
Mk "$w147/component_crx_cache/x" "crx`n"
Mk "$p147/package.json" "{`"name`":`"proj`"}`n"
Mk "$p147/node_modules/m/index.js" "module`n"
Mk "$k147/m/.git/HEAD" "ref: refs/heads/main`n"
foreach ($s147 in @('s1', 's2', 's3')) {
  Mk "$d147/session-state/$s147/events.jsonl" "{`"type`":`"session.start`"}`n"
}
Mk "$d147/session-state/s4/workspace.yaml" "cwd: C:\\coppool`nclient_name: github/autopilot`n"
Mk 'coppool/AGENTS.md' '# pool'

# 2026-10-17 session sync round (#153)
# Credential files the session sync research found unflagged: nanobot's
# remote WebUI pairing keys, Agent Zero's plugin configuration (home, native
# and a0_usr volume forms), Cline's cached remote config and webhook config,
# Gemini CLI's /bug-memory heap snapshot, little-coder's legacy config with
# its gist token, and Qwen Code's channel credential files, whose routing
# files (sessions.json, routes.json) stay unflagged. Cline's globalStorage
# cache is collected (its sync queue is evidence), and so is Kilo's log
# directory. Checks follow the default and -NoSecrets runs below; the same
# files are in smoke.sh under alice.
$n153 = 'Users/alice/.nanobot/webui/remote-pairing/11111111-1111-4111-8111-111111111111'
$g153 = 'Users/alice/.vscode-server/data/User/globalStorage/saoudrizwan.claude-dev/cache'
$t153 = 'plugins/_telegram_integration/config.json'
$v153 = 'var/lib/docker/volumes/a0_usr/_data'
Mk "$n153/identity" "key`n"
Mk "$n153/exchange" "key`n"
Mk "$n153/request" "{}`n"
Mk "Users/alice/agent-zero/main/usr/$t153" '{"token":"x"}'
Mk "Users/alice/Desktop/agent-zero/usr/$t153" '{"token":"x"}'
Mk "$v153/$t153" '{"token":"x"}'
Mk "$v153/usr/$t153" '{"token":"x"}'
Mk "$g153/remote_config_org1.json" "{`"promptUploading`":{}}`n"
Mk "$g153/sync-queue.json" "{`"items`":{}}`n"
Mk 'Users/alice/Documents/Cline/webhook_config.json' "{`"webhook_token`":`"x`"}`n"
Mk 'Users/alice/.gemini/tmp/gem/bug-memory-1792000000000.heapsnapshot' "heap`n"
Mk 'Users/alice/.little-coder/config.json' "{`"gist_token`":`"x`"}`n"
Mk 'Users/alice/.qwen/channels/qqbot-credentials.json' "{`"appId`":`"x`",`"appSecret`":`"x`"}`n"
Mk 'Users/alice/.qwen/channels/weixin/account.json' "{`"token`":`"x`"}`n"
Mk 'Users/alice/.qwen/channels/sessions.json' "{}`n"
Mk 'Users/alice/.qwen/channels/daemon/0123abcd/routes.json' "{}`n"
Mk 'Users/alice/.local/share/kilo/log/2026-10-17T120000.log' "INFO creating session`n"

# 2026-10-18 Codex shell snapshots (#160)
# Codex Desktop inside the ChatGPT app (build 26.1013.40934, macOS,
# 2026-10-18) writes .codex/shell_snapshots/<thread uuid>.<unix ns>.sh, the
# user's exported shell environment replayed for the sandbox, so any API key
# the login shell exports lands there. Flagged secret since 1.15.0. Checks
# follow the default and -NoSecrets runs below; the same file is in smoke.sh
# under alice.
$s160 = 'Users/alice/.codex/shell_snapshots/22222222-2222-4222-8222-222222222222.1792000000000000000.sh'
Mk $s160 "# Snapshot file`nexport EXAMPLE_API_KEY=x`n"

# 2026-10-19 Codex projectless output directories (#149)
# The ChatGPT desktop app (Windows 2026-10-15, macOS 2026-10-15 and
# 2026-10-18) runs a thread
# with no project in Documents/Codex/<date>/<slug>, with work/ and outputs/
# inside, and records that directory as the rollout cwd. Since 1.16.0 the
# directory is a codex-cli catalog line and discovery drops it as a project;
# alice's rollout keeps its Documents\app project. Checks follow the default
# run and the inventory below; the same files are in smoke.sh under bob.
$w149 = 'home/bob/Documents/Codex/2026-10-18/w'
Mk 'home/bob/.codex/sessions/2026/10/03/rollout-2.jsonl' '{"type":"session_meta","payload":{"cwd":"/home/bob/Documents/Codex/2026-10-18/w"}}'
Mk "$w149/outputs/report.md" "# report`n"
Mk "$w149/work/notes.txt" "notes`n"

# 2026-10-20 Cursor IDE round on macOS (#6)
# Cursor 3.25.9 and 3.26.13 (macOS, 2026-10-19 and 2026-10-20) keep
# per-account and per-conversation sync stores under AgentStores and one
# directory per in-app update under update-supervisor (events.jsonl, the
# build that ran when, beside the 484 KB supervisor binary). The IDE's
# agent worker embeds a copy of the Agent CLI under agent-cli in
# globalStorage, and ~/.cursor holds canvas type declarations under
# node_modules and a feature-flag cache copied from the server: those are
# excluded; the worker's own files and the agent transcripts stay collected.
# Checks follow the default run below; the same files are in smoke.sh
# under bob.
$c6 = 'Users/alice/Library/Application Support/Cursor'
$w6 = "$c6/User/globalStorage/anysphere.cursor-agent-worker"
$u6 = "$c6/update-supervisor/33333333-3333-4333-8333-333333333333"
Mk "$c6/AgentStores/cursor_agent_stores/u1/.sync/index.sqlite" "sqlite`n"
Mk "$c6/AgentStores/cursor_agent_stores/.control/u1/pins/1-x.json" "{`"purpose`":`"foreground`"}`n"
Mk "$u6/events.jsonl" "{`"type`":`"supervisor_started`"}`n"
Mk "$u6/cursor-update-supervisor" "binary`n"
Mk "$w6/agent-cli/.local/share/x" "cli`n"
Mk "$w6/cursor-agent-worker-1.log" "worker log`n"
Mk 'Users/alice/.cursor/projects/p/canvases/node_modules/x.d.ts' "declare const x: number;`n"
Mk 'Users/alice/.cursor/projects/p/agent-transcripts/u/u.jsonl' "{`"type`":`"turn_ended`",`"status`":`"success`"}`n"
Mk 'Users/alice/.cursor/statsig-cache.json' "{}`n"

# 2026-10-20 Cursor IDE round on Ubuntu (#236)
# Cursor 3.25.9 (Ubuntu arm64 deb, 2026-10-20) keeps the same sync stores
# under the XDG state directory, .local/state/cursor/agent-stores, not under
# .config/Cursor. Checks follow the default run below; the same files are in
# smoke.sh under alice.
$l236 = 'home/bob/.local/state/cursor/agent-stores/cursor_agent_stores'
Mk "$l236/u1/.sync/index.sqlite" "sqlite`n"
Mk "$l236/.control/u1/pins/1-x.json" "{`"purpose`":`"foreground`"}`n"

# 2026-10-21 Cursor IDE round on Windows (#236)
# Cursor 3.26.13 (Windows 11 arm64, per-user installer, 2026-10-21) keeps
# the sync stores under %LOCALAPPDATA%\Cursor\AgentStores, not beside the
# user-data directory in AppData/Roaming, and extracts the worker's Agent
# CLI copy (262.7 MB) under agent-cli in AppData/Roaming/Cursor, which is
# excluded while the worker's log beside it stays collected. Checks follow
# the default run below; the same files are in smoke.sh under bob.
$s236 = 'Users/alice/AppData/Local/Cursor/AgentStores/cursor_agent_stores'
$w236 = 'Users/alice/AppData/Roaming/Cursor/User/globalStorage/anysphere.cursor-agent-worker'
Mk "$s236/u1/.sync/index.sqlite" "sqlite`n"
Mk "$s236/.control/u1/pins/1-x.json" "{`"purpose`":`"foreground`"}`n"
Mk "$w236/agent-cli/x" "cli`n"
Mk "$w236/cursor-agent-worker-1.log" "worker log`n"
# Cursor 3.26.13 (W21, 2026-10-21) put an installed plugin's marketplace copy
# under .cursor/plugins/cache/<marketplace>/<plugin>/<sha>, excluded like the
# Claude Code and Codex plugin caches; plugins/local beside it is collected.
$p236 = 'Users/alice/.cursor/plugins'
Mk "$p236/cache/cursor-public/x/0123abcd/mcp.json" "{`"mcpServers`":{}}`n"
Mk "$p236/local/x.json" "{}`n"
# Cursor 3.26.16 (W25, 2026-10-21): the update that brought it wrote
# update-supervisor/win32/<installationId>/ with app-ready.json, state.json
# and a copy of inno_updater.exe (3.4 MB), which is excluded.
$u236 = 'Users/alice/AppData/Roaming/Cursor/update-supervisor/win32/0000'
Mk "$u236/inno_updater.exe" "binary`n"
Mk "$u236/app-ready.json" "{`"currentVersion`":`"x`"}`n"
Mk "$u236/state.json" "{`"stage`":`"x`"}`n"
# 2026-10-21 OpenHands Agent Canvas credentials and workspaces (#218)
# Agent Canvas (OpenHands/OpenHands 8d39305, scripts/mars-credentials.mjs)
# keeps its DigitalOcean connections in mars-credentials.json in the Electron
# user data directory, and Canvas-in-Docker unpacks automation runs under
# ~/.openhands/workspaces (docker/entrypoint.sh), excluded like
# agent-canvas/workspaces; workspaces.json beside it stays collected. Checks
# follow the default run below; the same files are in smoke.sh under alice
# and bob.
$m218 = @(
  'Users/alice/AppData/Roaming/OpenHands Agent Canvas/mars-credentials.json',
  'Users/alice/Library/Application Support/OpenHands Agent Canvas/mars-credentials.json',
  'Users/alice/.config/OpenHands Agent Canvas/mars-credentials.json'
)
foreach ($f218 in $m218) { Mk $f218 "{`"version`":1,`"connections`":[]}`n" }
Mk 'Users/alice/.openhands/workspaces/run1/f' "x`n"

# 2026-10-21 Agent Zero source review (#217)
# The WhatsApp bridge's Baileys login state under the install's tmp/ (home,
# Desktop and volume-relative forms), an editor (ACP) chat whose workspace
# and extra folder are discovered as projects, and a computer-use screen
# capture of the A0 CLI connector in the Windows temp directory. Checks
# follow the default and -NoSecrets runs below; the same files are in
# smoke.sh, the capture under bob.
$w217 = 'tmp/whatsapp/session/creds.json'
$t217 = 'Users/alice/AppData/Local/Temp/_a0_connector/computer_use/ctx1/0000.png'
Mk "Users/alice/agent-zero/main/$w217" '{}'
Mk "Users/alice/Desktop/agent-zero/$w217" '{}'
Mk "var/lib/docker/volumes/a0_usr/_data/$w217" '{}'
Mk 'Users/alice/agent-zero/main/usr/chats/acp1/chat.json' ('{"id": "acp1", "data": ' +
  '{"acp_cwd": "/srv/a0acp", "acp_additional_directories": ["/srv/a0extra"]}}')
Mk 'srv/a0acp/AGENTS.md' '# acp'
Mk 'srv/a0extra/AGENTS.md' '# extra'
Mk $t217 'png'

# 2026-10-21 framework catalog gaps (#223, #224, #225)
# From source, no real install: CrewAI's project-local .crewai/last_run.json,
# its mark of a run traced to AMP, in a discovered project; difyctl's pending
# device login, login-pending.yml, in its three config directories; and the
# CLAI 2.0 state directory .local/state/pydantic-clai2 with the web
# orchestrator's conversation, a workspace record, its token and session.log,
# and a clone of a remote repository, which is excluded. Checks follow the
# default and -NoSecrets runs below; the same files are in smoke.sh.
Mk 'proj/.crewai/last_run.json' "{`"execution_id`":`"x`",`"tier`":`"ephemeral`"}`n"
foreach ($d224 in @('.config', 'AppData/Roaming', 'AppData/Local')) {
  Mk "Users/alice/$d224/difyctl/login-pending.yml" "device_code: x`n"
}
$p225 = 'Users/alice/.local/state/pydantic-clai2'
Mk "$p225/orchestrator.json" "{}`n"
Mk "$p225/workspaces/registry/ws1/workspace.json" "{`"id`":`"ws1`"}`n"
Mk "$p225/workspaces/registry/ws1/token" "token`n"
Mk "$p225/workspaces/registry/ws1/session.log" "log`n"
Mk "$p225/workspaces/clones/repo-0123456789/.git/HEAD" "ref: refs/heads/main`n"

# 2026-10-21 Codex worktree cwds and archived threads (#222)
# Codex (source at 4e7b9e2) runs a desktop thread in its own git worktree,
# ~/.codex/worktrees/<4 hex>/<repo>, excluded by the catalog, and moves an
# archived thread's rollout flat into ~/.codex/archived_sessions; Open
# Interpreter keeps the same worktree layout under ~/.openinterpreter.
# Discovery drops a worktree cwd and reads the archive. Checks follow the
# default run below; the same files are in smoke.sh (Codex under bob, Open
# Interpreter under alice).
Mk 'home/bob/.codex/archived_sessions/rollout-2026-10-01T00-00-00-a1.jsonl' '{"type":"session_meta","payload":{"cwd":"C:\\codexarch"}}'
Mk 'codexarch/AGENTS.md' "# agents`n"
Mk 'home/bob/.codex/sessions/2026/10/03/rollout-3.jsonl' '{"type":"session_meta","payload":{"cwd":"/home/bob/.codex/worktrees/a1b2/repo"}}'
Mk 'home/bob/.codex/worktrees/a1b2/repo/AGENTS.md' "# agents`n"
Mk 'Users/alice/.openinterpreter/sessions/2026/10/04/rollout-2026-10-04T00-00-00-u3.jsonl' '{"type":"session_meta","payload":{"cwd":"C:\\Users\\alice\\.openinterpreter\\worktrees\\c3d4\\repo"}}'
Mk 'Users/alice/.openinterpreter/worktrees/c3d4/repo/AGENTS.md' "# agents`n"

# 2026-10-21 Cody JetBrains plugin files (#214)
# Source-derived (sourcegraph/cody-public-snapshot at 8e20ac6): the plugin's
# application components in each IDE's options/ directory, ~/.sourcegraph and
# a project's .idea/.sourcegraph settings, and the legacy project-level
# .idea/cody_history.xml. cody_accounts.xml carries customRequestHeaders and
# is flagged; cody_accounts_settings.xml holds only the active account id.
# Checks follow the default and -NoSecrets runs below; the same files, in the
# Linux layout, are in smoke.sh.
$o214 = 'Users/alice/AppData/Roaming/JetBrains/IntelliJIdea2025.2/options'
Mk "$o214/cody.xml" "<application />`n"
Mk "$o214/cody_accounts.xml" "<application />`n"
Mk "$o214/cody_accounts_settings.xml" "<application />`n"
Mk "$o214/cody_application_settings.xml" "<application />`n"
Mk 'Users/alice/.sourcegraph/cody_settings.json' "{}`n"
Mk 'proj/.idea/cody_history.xml' "<project version=`"4`" />`n"
Mk 'proj/.idea/.sourcegraph/cody_settings.json' "{}`n"

# 2026-10-21 agent worktrees inside a project (#216)
# Gemini CLI's --worktree creates <project>/.gemini/worktrees/<name>
# (google-gemini/gemini-cli 3be3d44, worktreeService.ts) and Qwen Code's
# enter_worktree <project>/.qwen/worktrees/<slug> (QwenLM/qwen-code 5dcf7c7,
# worktreeSessionService.ts): full git checkouts that the project entries
# collected whole. Both are excluded, as .claude/worktrees and
# .kilo/worktrees are; the project's .gemini/settings.json beside them stays
# collected. Checks follow the default run below; the same files are in
# smoke.sh under /srv/gem.
Mk 'gem/.gemini/worktrees/w1/f' "wt`n"
Mk 'gem/.qwen/worktrees/w1/f' "wt`n"
Mk 'gem/.gemini/settings.json' "{}`n"

# 2026-10-21 Hermes quick snapshots and desktop connections (#123, #208)
# hermes-agent 86fa9e6 (source only): a quick snapshot under state-snapshots
# holds an older state.db, the only copy of a pruned or deleted session, so
# it is collected, while the credential copies beside it (.env, auth.json,
# the pairing stores) stay flagged by the home-relative secret globs. The
# desktop app's connection.json and connections.json can hold a gateway
# token in plain text and are flagged. Checks follow the default and
# -NoSecrets runs below; the same files are in smoke.sh under alice.
$q123 = 'Users/alice/.hermes/state-snapshots/20261001-120004-pre-update'
$w123 = 'Users/alice/AppData/Local/hermes/state-snapshots/20261001-120004'
Mk "$q123/state.db" "sqlite`n"
Mk "$q123/manifest.json" "{`"id`":`"20261001-120004-pre-update`"}`n"
Mk "$q123/.env" "KEY=x`n"
Mk "$q123/auth.json" "{`"providers`":{}}`n"
Mk "$q123/pairing/telegram-approved.json" "{`"42`":{`"user_name`":`"u`"}}`n"
Mk "$w123/state.db" "sqlite`n"
Mk 'Users/alice/.config/Hermes/connections.json' "{`"connections`":[]}`n"

# 2026-10-21 nanobot workspace cron and triggers (#220)
# nanobot (HKUDS/nanobot at 909b277, source only) keeps its cron jobs and
# local triggers in the workspace, with one run record per run (session
# key, prompt, reply) that outlives the session. The project catalog
# collects the job and trigger files and the runs directories of a
# discovered workspace; the trigger queue (inbox/) is left. Checks follow
# the default run below; the same files are in smoke.sh under srv/nanows.
Mk 'nanows/cron/jobs.json' "{`"jobs`":[]}`n"
Mk 'nanows/cron/runs/j1_1_ab.json' "{`"job_id`":`"j1`",`"status`":`"ok`"}`n"
Mk 'nanows/triggers/triggers.json' "{`"triggers`":[]}`n"
Mk 'nanows/triggers/runs/d1.json' "{`"trigger_id`":`"t1`",`"status`":`"ok`"}`n"
Mk 'nanows/triggers/inbox/d2.json' "{`"id`":`"d2`"}`n"

# 2026-10-21 OpenClaw source review (#219)
# OpenClaw 2026.10.5 (source, openclaw/openclaw at 146284a) keeps the
# approvals socket token in the legacy exec-approvals.json, and the Docker
# install's ~/.openclaw-auth-profile-secrets holds gateway.env: both are
# flagged, and so is a volume-relative exec-approvals.json. A Gateway clone
# under projects/<16 hex>/<name> is excluded while another projects entry is
# collected, and the volume-relative forms of the clone, plugin-skills and
# agent tmp exclusions prune the same names in a volume (the a0_usr one
# here), whose own projects/<name> stays collected. Checks follow the
# default and -NoSecrets runs below; the same files are in smoke.sh under
# alice.
$o219 = 'Users/alice/.openclaw'
$c219 = '0123456789abcdef'
$v219 = 'var/lib/docker/volumes/a0_usr/_data'
Mk "$o219/exec-approvals.json" "{`"socket`":{`"token`":`"x`"}}`n"
Mk 'Users/alice/.openclaw-auth-profile-secrets/gateway.env' "OPENAI_API_KEY=x`n"
Mk "$o219/projects/$c219/repo/README.md" "clone`n"
Mk "$o219/projects/notes/todo.md" "notes`n"
Mk "$v219/exec-approvals.json" "{`"socket`":{`"token`":`"x`"}}`n"
Mk "$v219/projects/$c219/repo/README.md" "clone`n"
Mk "$v219/projects/p219/notes.md" "project`n"
Mk "$v219/plugin-skills/s" "link`n"
Mk "$v219/agents/main/agent/tmp/t" "tmp`n"
Mk "$v219/agents/main/agent/.tmp/t" "tmp`n"

# 2026-10-21 OpenCode and Kilo Code source review (#213, #221)
# Source only, no real install: OpenCode 2.0 (anomalyco/opencode cb07c55)
# writes its background server's password to service.json, or
# service-<channel>.json, in the config and the state directory, keeps the
# Electron desktop app's data in ai.opencode.desktop, .beta or .dev under
# the platform's app data directory with a V8 compile-cache, and keeps a
# temp root that is AppData/Local/Temp/opencode on Windows. Kilo Code
# (Kilo-Org/kilocode 87cc35c) writes its sandbox policy and preference files
# beside its state directory. Checks follow the default and -NoSecrets runs
# below; the same files are in smoke.sh under alice and bob.
$d213 = 'Users/alice/Library/Application Support/ai.opencode.desktop'
$k221 = 'Users/alice/.local/state/kilo-sandbox-policy/aa'
Mk 'Users/alice/.config/opencode/service.json' "{`"password`":`"x`"}`n"
Mk 'Users/alice/.local/state/opencode/service-local.json' "{`"password`":`"x`"}`n"
Mk "$d213/drafts.sqlite" "sqlite`n"
Mk "$d213/compile-cache/x" "v8`n"
Mk 'Users/alice/.config/ai.opencode.desktop.beta/drafts.sqlite' "sqlite`n"
Mk 'Users/alice/AppData/Roaming/ai.opencode.desktop/drafts.sqlite' "sqlite`n"
Mk 'Users/alice/AppData/Local/Temp/opencode/notes.txt' "tmp`n"
Mk "$k221/bb.json" "{`"enabled`":true,`"mode`":`"deny`",`"version`":1}`n"
Mk 'Users/alice/.local/state/kilo-sandbox-preference/bb.json' "false`n"

# 2026-10-21 Qwen Code session registry (#230)
# Qwen Code writes ~/.qwen/sessions/<pid>.json (or <pid>-<8 hex>.json) per
# running session, with ipcToken, the token that admits a connection to the
# session's socket, so the directory is a secret glob. Checks follow the
# default and -NoSecrets runs below; the same files are in smoke.sh.
Mk 'Users/alice/.qwen/sessions/4242.json' "{`"sessionId`":`"x`",`"ipcToken`":`"x`"}`n"
Mk 'Users/alice/.qwen/sessions/4243-0123abcd.json' "{`"sessionId`":`"x`",`"ipcToken`":`"x`"}`n"

# 2026-10-21 Roo Code CLI cloud credentials (#159)
# The Roo Code CLI up to 3.53.0 saved its Roo Code Cloud token in
# ~/.roo/cli-credentials.json (apps/cli/src/lib/storage/credentials.ts at
# Roo-Code v3.53.0); the secret glob flags it. Checks follow the default run
# below; the same file is in smoke.sh under alice.
Mk 'Users/alice/.roo/cli-credentials.json' "{`"token`":`"not-a-real-token`"}`n"

# 2026-10-21 Twinny workspace storage (#215)
# Twinny 4.3.15 (source, twinnydotdev/twinny 0337b265) keeps one
# agent-changes/<uuid>.json record per agent-mode reply that changed files
# in its per-workspace extension storage, workspaceStorage/<id>/
# rjmacarthy.twinny, beside the editor's own workspace.json and
# state.vscdb. The nested twinny entries claim that directory from the
# editor's walk; the files beside it stay vscode. Checks follow the default
# run below; the same files are in smoke.sh under alice.
$t215 = 'Users/alice/AppData/Roaming/Code/User/workspaceStorage/ws215'
Mk "$t215/rjmacarthy.twinny/agent-changes/c1.json" "{`"id`":`"c1`",`"root`":`"C:\\twinproj`",`"createdAt`":1,`"files`":[]}`n"
Mk "$t215/workspace.json" "{`"folder`":`"file:///c%3A/twinproj`"}`n"
# The twinny-server forge plugins (GitHub, GitLab, Gitea, Bitbucket) keep
# their saved access tokens beside the watched repositories in
# plugins/<id>/repos.json, flagged secret.
Mk 'Users/alice/.twinny/server/plugins/github/repos.json' "{`"version`":1,`"repos`":[],`"tokens`":[]}`n"

# 2026-10-21 project git metadata (#253)
# Every discovered project's .git/HEAD, config, FETCH_HEAD, packed-refs,
# refs/, logs/ and worktrees/ are collected under agent project: the
# remotes with their fetch and push URLs, the checked-out branch, the last
# fetch, the branches and tags, the reflog and the linked worktrees. The
# object store, the index, hooks, LFS objects and submodule repositories
# match no PROJECT_CATALOG line and get no row. Checks follow the default
# run below; the same files are in smoke.sh under the project /srv/proj.
$g253 = 'proj/.git'
$oid253 = '1111111111111111111111111111111111111111'
$tag253 = '2222222222222222222222222222222222222222'
$zero253 = '0000000000000000000000000000000000000000'
$cfg253 = @(
  '[core]', "`trepositoryformatversion = 0", "`tbare = false",
  '[remote "origin"]', "`turl = https://git.example.com/acme/proj.git",
  "`tpushurl = git@git.example.com:acme/proj.git",
  "`tfetch = +refs/heads/*:refs/remotes/origin/*",
  '[remote "upstream"]', "`turl = https://git.example.org/upstream/proj.git",
  "`tfetch = +refs/heads/*:refs/remotes/upstream/*",
  '[branch "main"]', "`tremote = origin", "`tmerge = refs/heads/main"
)
Mk "$g253/HEAD" "ref: refs/heads/main`n"
Mk "$g253/config" (($cfg253 -join "`n") + "`n")
Mk "$g253/FETCH_HEAD" "$oid253`t`tbranch 'main' of https://git.example.com/acme/proj`n"
Mk "$g253/packed-refs" "# pack-refs with: peeled fully-peeled sorted`n$tag253 refs/tags/v1`n"
Mk "$g253/refs/heads/main" "$oid253`n"
Mk "$g253/refs/remotes/origin/main" "$oid253`n"
Mk "$g253/logs/HEAD" "$zero253 $oid253 A <a@example.com> 1759449600 +0000`tclone: from https://git.example.com/acme/proj.git`n"
Mk "$g253/logs/refs/remotes/origin/main" "$zero253 $oid253 A <a@example.com> 1759449600 +0000`tfetch: fast-forward`n"
Mk "$g253/worktrees/wt1/HEAD" "ref: refs/heads/wt1`n"
Mk "$g253/worktrees/wt1/gitdir" "C:/proj-wt1/.git`n"
Mk "$g253/worktrees/wt1/index" "DIRC`n"
Mk "$g253/worktrees/wt1/index.lock" "DIRC`n"
Mk "$g253/worktrees/wt1/sharedindex.3333333333333333333333333333333333333333" "DIRC`n"
Mk "$g253/worktrees/wt1/modules/sub/HEAD" "ref: refs/heads/main`n"
Mk "$g253/worktrees/wt1/modules/sub/objects/ab/cdef" "object`n"
Mk "$g253/objects/ab/cdef" "object`n"
Mk "$g253/index" "DIRC`n"
Mk "$g253/hooks/pre-commit.sample" "#!/bin/sh`n"
Mk "$g253/lfs/objects/x" "lfs`n"
Mk "$g253/modules/sub/HEAD" "ref: refs/heads/main`n"

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
# files are in smoke.sh under alice and the project /srv/proj.
$t256 = 'Users/alice/AppData/Local/Temp/claude/C--proj/25625625-6256-4256-8256-256256256256'
Mk "$t256/scratchpad/notes.txt" "scratch`n"
Mk "$t256/tasks/b256b256b.output" "done`n"
Mk 'Users/alice/.claude.json.backup' "{`"oauthAccount`":{}}`n"
Mk 'Users/alice/.claude/daemon/control.key' '0123456789abcdef0123456789abcdef'
Mk 'Users/alice/.claude/daemon/pipe.key' '0123456789abcdef'
Mk 'Users/alice/.claude/daemon/roster.json' "{`"proto`":1,`"workers`":{}}`n"
Mk 'Users/alice/.claude/backups/.claude.json.backup.1792800000000' "{`"oauthAccount`":{}}`n"
Mk 'Users/alice/.claude/backups/.claude.json.corrupted.2026-10-23T17-00-00-000Z' "{`"oauthAccount`":{}}`n"
Mk 'Users/alice/.claude/paste-cache/0123456789abcdef.txt' "pasted text`n"
Mk 'Users/alice/.claude/plugins/plugin-directory-cache-v2.json' "{`"plugins`":[]}`n"
Mk "$g253/info/exclude" "# git ls-files --others --exclude-from=.git/info/exclude`n.claude/scheduled_tasks.lock`n"

# 2026-10-26 claude-code Linux round (#256)
# Claude Code 2.1.310 on Ubuntu 26.04 (real install, 2026-10-25/26) holds
# .local/state/claude/locks/<version>.lock, a JSON lock with acquiredAt,
# execPath, pid and version, while a session runs, and creates
# .cache/claude/staging/ at install; both directories are home-relative on
# Windows too and are collected as claude-code. Checks follow the default
# run below; the same files are in smoke.sh under alice.
Mk 'Users/alice/.local/state/claude/locks/2.1.310.lock' "{`"acquiredAt`":1792800000000,`"execPath`":`"/x`",`"pid`":1,`"version`":`"2.1.310`"}`n"
Mk 'Users/alice/.cache/claude/staging/entry' "staged`n"

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
# files are in smoke.sh under alice.
$u256 = 'Users/alice/Applications/Claude Code URL Handler.app/Contents'
$s256 = 'bridge-spawn/cse_0123456789abcdef0123'
Mk "$u256/Info.plist" "<plist version=`"1.0`"><dict><key>CFBundleURLSchemes</key></dict></plist>`n"
foreach ($d256 in @('Users/alice/.claude', 'Users/alice/.claude-work')) {
  Mk "$d256/ide/53256.lock" "{`"authToken`":`"00000000-0000-4000-8000-000000000256`",`"transport`":`"ws`"}`n"
  Mk "$d256/$s256/mcp.json" "{`"mcpServers`":{`"claude-code-remote`":{`"headers`":{`"X-Session-UUID`":`"x`"}}}}`n"
}
Mk "Users/alice/.claude/$s256/append-system-prompt.txt" "appended system prompt`n"
$link256 = $false
try {
  New-Item -ItemType Directory -Path (P "$u256/MacOS") -Force | Out-Null
  $target256 = [System.IO.Path]::Combine('..', '..', '..', '..', '.local', 'bin', 'claude')
  New-Item -ItemType SymbolicLink -Path (P "$u256/MacOS/claude") -Target $target256 -ErrorAction Stop | Out-Null
  $link256 = $true
} catch { Write-Output 'note: symlink creation not permitted here, #256 URL handler symlink check skipped' }

# 2026-10-15 special files (#120)
# Codex CLI 0.162.1 keeps Unix domain sockets under .codex; on Windows each
# is a reparse point (tag IO_REPARSE_TAG_AF_UNIX) with an empty LinkType,
# which 1.12.0 recorded as a symlink to itself. The socket gets one
# skipped_special row, type 'other' on Windows (PowerShell exposes no
# reparse tag) and 'socket' elsewhere. UnixDomainSocketEndPoint exists only
# in PowerShell 7 (.NET Core); under 5.1 a minimal EndPoint subclass builds
# the address. The socket is bound from inside its directory, so a long temp
# path cannot pass the socket path limit, and kept open until the checks
# after the default run. The FIFO of smoke.sh is not here: PowerShell cannot
# create one. When no socket can be bound, the socket checks are skipped.
$sock120Rel = 'Users/alice/.codex/app-server-daemon/daemon-updater.sock'
$sock120 = $null
$endPoint120Source = @'
using System.Net;
using System.Net.Sockets;
using System.Text;
public class Cac120UnixEndPoint : EndPoint {
  private readonly string path;
  public Cac120UnixEndPoint(string path) { this.path = path; }
  public override AddressFamily AddressFamily { get { return AddressFamily.Unix; } }
  public override SocketAddress Serialize() {
    byte[] bytes = Encoding.UTF8.GetBytes(path);
    SocketAddress address = new SocketAddress(AddressFamily.Unix, 110);
    for (int i = 0; i < bytes.Length; i++) { address[2 + i] = bytes[i]; }
    return address;
  }
  public override EndPoint Create(SocketAddress address) { return new Cac120UnixEndPoint(path); }
}
'@
try {
  $dir120 = [System.IO.Path]::GetDirectoryName((P $sock120Rel))
  [void][System.IO.Directory]::CreateDirectory($dir120)
  $endPoint120Type = 'System.Net.Sockets.UnixDomainSocketEndPoint' -as [type]
  if (-not $endPoint120Type) {
    if (-not ('Cac120UnixEndPoint' -as [type])) { Add-Type -TypeDefinition $endPoint120Source }
    $endPoint120Type = 'Cac120UnixEndPoint' -as [type]
  }
  $socketArgs120 = @([System.Net.Sockets.AddressFamily]::Unix,
    [System.Net.Sockets.SocketType]::Stream, [System.Net.Sockets.ProtocolType]::Unspecified)
  $sock120 = New-Object System.Net.Sockets.Socket -ArgumentList $socketArgs120
  $cwd120 = [Environment]::CurrentDirectory
  try {
    [Environment]::CurrentDirectory = $dir120
    $sock120.Bind((New-Object $endPoint120Type.FullName -ArgumentList 'daemon-updater.sock'))
  } finally { [Environment]::CurrentDirectory = $cwd120 }
} catch {
  if ($sock120) { $sock120.Close() }
  $sock120 = $null
  Write-Output "note: no Unix domain socket could be created ($($_.Exception.Message)); socket checks skipped"
}
$Miss = Test-Made
Check "every main-image fixture was created ($($Miss.Count) missing$(if ($Miss.Count) { ', first ' + $Miss[0] }))" { $Miss.Count -eq 0 }
Check '#77 deep fixture path is longer than 260 characters' { (P $Deep77).Length -gt 260 }

# ---- runner ---------------------------------------------------------------
function Run([string]$name, [hashtable]$extra) {
  $o = Join-Path $Out $name
  New-Item -ItemType Directory -Path $o -Force | Out-Null
  $cargs = @{ Root = $Root; OutputDir = $o; Quiet = $true; MaxFileSizeMB = 1 }
  foreach ($k in $extra.Keys) { $cargs[$k] = $extra[$k] }
  $global:LASTEXITCODE = 0
  $script:stdout = & $Collector @cargs 2>&1 | Out-String
  $script:rc = $LASTEXITCODE
  $script:M = Get-ChildItem -LiteralPath $o -Filter '*.manifest.jsonl' | Select-Object -First 1
  $script:A = Get-ChildItem -LiteralPath $o | Where-Object { $_.Name -match '\.(tar\.gz|zip)$' } | Select-Object -First 1
  $script:S = Get-ChildItem -LiteralPath $o -Filter '*.collection.json' | Select-Object -First 1
  $script:Rows = @()
  if ($script:M) { $script:Rows = @(Get-Content -LiteralPath $script:M.FullName | ForEach-Object { $_ | ConvertFrom-Json }) }
}
function Row([string]$suffix) {
  $s = $suffix.Replace('\', '/')
  return ($script:Rows | Where-Object { ($_.path -replace '\\', '/').ToLowerInvariant().EndsWith($s.ToLowerInvariant()) } | Select-Object -First 1)
}
function StatusOf([string]$suffix) { $r = Row $suffix; if ($r) { return $r.status } else { return '' } }
function ArchiveEntries {
  if ($script:A.Name -like '*.tar.gz') { return @(& tar -tzf $script:A.FullName 2>$null) }
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $z = [System.IO.Compression.ZipFile]::OpenRead($script:A.FullName)
  try { return @($z.Entries | ForEach-Object { $_.FullName }) } finally { $z.Dispose() }
}

# 2026-10-07 (#72): reads a .tar.gz with .NET, so names outside the ANSI code
# page can be checked on Windows too, where tar.exe cannot list them. Returns
# the members (name, type, size, link and, for files, sha256) with pax path,
# linkpath and size records applied, how many headers had a wrong checksum,
# and whether the archive ends with two zero blocks.
function Read-TarGz([string]$file) {
  $fsIn = [System.IO.File]::OpenRead($file)
  $gz = New-Object System.IO.Compression.GZipStream($fsIn, [System.IO.Compression.CompressionMode]::Decompress)
  $ms = New-Object System.IO.MemoryStream
  try { $gz.CopyTo($ms) } finally { $gz.Dispose() }
  $b = $ms.ToArray()
  $utf8 = New-Object System.Text.UTF8Encoding $false
  $sha = [System.Security.Cryptography.SHA256]::Create()
  $members = @(); $badSum = 0; $zeros = 0; $pos = 0; $pax = @{}
  $str = { param($o, $l) $e = $o; while ($e -lt $o + $l -and $b[$e] -ne 0) { $e++ }; $utf8.GetString($b, $o, $e - $o) }
  while ($pos + 512 -le $b.Length) {
    $hdr = New-Object byte[] 512; [Array]::Copy($b, $pos, $hdr, 0, 512)
    if ([System.Linq.Enumerable]::Sum([int[]]$hdr) -eq 0) { $zeros++; $pos += 512; if ($zeros -eq 2) { break }; continue }
    $zeros = 0
    $want = [Convert]::ToInt64((& $str ($pos + 148) 8).Trim(), 8)
    for ($i = 148; $i -lt 156; $i++) { $hdr[$i] = 32 }
    if ([System.Linq.Enumerable]::Sum([int[]]$hdr) -ne $want) { $badSum++ }
    $type = [string][char]$b[$pos + 156]
    $size = [Convert]::ToInt64((& $str ($pos + 124) 12).Trim(), 8)
    if ($pax.ContainsKey('size')) { $size = [int64]$pax['size'] }
    $data = $pos + 512
    if ($type -eq 'x') {
      # Records are "<len> key=value\n", len in bytes and counting itself.
      $p = $data
      while ($p -lt $data + $size) {
        $sp = $p; while ($b[$sp] -ne 32) { $sp++ }
        $len = [int]$utf8.GetString($b, $p, $sp - $p)
        $kv = $utf8.GetString($b, $sp + 1, $p + $len - $sp - 2); $eq = $kv.IndexOf('=')
        $pax[$kv.Substring(0, $eq)] = $kv.Substring($eq + 1)
        $p += $len
      }
    } else {
      $name = & $str $pos 100; $prefix = & $str ($pos + 345) 155
      if ($prefix) { $name = $prefix + '/' + $name }
      $link = & $str ($pos + 157) 100
      if ($pax.ContainsKey('path')) { $name = $pax['path'] }
      if ($pax.ContainsKey('linkpath')) { $link = $pax['linkpath'] }
      $h = ''
      if ($type -eq '0') { $h = ([BitConverter]::ToString($sha.ComputeHash($b, $data, [int]$size)) -replace '-', '').ToLower() }
      $members += [pscustomobject]@{ name = $name; type = $type; size = $size; link = $link; sha256 = $h }
      $pax = @{}
    }
    $pos = $data + [int]([Math]::Ceiling($size / 512) * 512)
  }
  return @{ members = $members; badsum = $badSum; end = ($zeros -eq 2) }
}
# A list as one string, sorted ordinally, so names that differ only by case
# compare in a fixed order.
function Join-Sorted($list) {
  $a = [string[]]@($list); [Array]::Sort($a, [StringComparer]::Ordinal)
  return ($a -join "`n")
}
# Every collected row's archived bytes, read from the extracted archive in
# $dir, match its sha256 and size; returns the number of files checked, or -1
# when one does not match.
function Test-ArchivedHashes([string]$dir) {
  $n = 0; $bad = 0
  foreach ($row in ($script:Rows | Where-Object { $_.status -eq 'collected' -and $_.archive_path })) {
    $f = XP (Join-Path $dir ($row.archive_path.Replace('/', $Sep)))
    if (-not (Test-Path -LiteralPath $f)) { $bad++; continue }
    if ((Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLower() -ne $row.sha256) { $bad++ }
    if ((Get-Item -LiteralPath $f -Force).Length -ne $row.size) { $bad++ }
    $n++
  }
  if ($bad -gt 0) { return -1 }
  return $n
}

# ---- default run ----------------------------------------------------------
Run 'default' @{}
$DefaultEntries = @(ArchiveEntries)
$dsum0 = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json
Check 'exit code 0' { $script:rc -eq 0 }
Check 'archive exists' { $null -ne $script:A -and $script:A.Length -gt 0 }
Check 'sha256 sidecar matches' { (Get-Content -LiteralPath "$($script:A.FullName).sha256").Split(' ')[0] -eq (Get-FileHash -LiteralPath $script:A.FullName -Algorithm SHA256).Hash.ToLower() }
Check 'transcript collected' { (StatusOf 'Users/alice/.claude/projects/-C-proj/s1.jsonl') -eq 'collected' }
$r = Row 'Users/alice/.claude/projects/-C-proj/s1.jsonl'
Check 'transcript hash correct' { $r -and $r.sha256 -eq (Get-FileHash -LiteralPath (P 'Users/alice/.claude/projects/-C-proj/s1.jsonl') -Algorithm SHA256).Hash.ToLower() }
Check 'transcript has owner and attributes fields' { $r -and $null -ne $r.owner -and $r.attributes -ne '' }
$r = Row 'Users/alice/.claude/.credentials.json'
Check 'secret collected and flagged' { $r -and $r.secret -eq $true -and $r.status -eq 'collected' }
Check 'antigravity token flagged secret' { (Row 'antigravity-cli/antigravity-oauth-token').secret -eq $true }
$r = Row 'Users/alice/.gemini/antigravity-cli/conversations/c1.db'
Check 'nested entry attributed to its own agent' { $r -and $r.agent -eq 'antigravity' }
Check 'nested entry collected exactly once' { @($script:Rows | Where-Object { $_.path -like '*antigravity-cli*conversations*c1.db' }).Count -eq 1 }
$r = Row 'Users/alice/.gemini/projects.json'
Check 'enclosing entry still attributed to gemini-cli' { $r -and $r.agent -eq 'gemini-cli' }
$r = Row 'Users/alice/AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/state/taskHistory.json'
Check 'cline globalStorage attributed to cline, not vscode' { $r -and $r.agent -eq 'cline' }
Check 'cline globalStorage collected exactly once' { @($script:Rows | Where-Object { $_.path -like '*Roaming*Code*User*globalStorage*saoudrizwan.claude-dev*taskHistory.json' }).Count -eq 1 }
$r = Row 'Users/alice/.claude/cache'
Check 'cache dir skipped_excluded with size' { $r -and $r.type -eq 'dir' -and $r.size -gt 0 -and $r.status -eq 'skipped_excluded' }
Check 'cache contents not collected' { $null -eq (Row 'cache/junk.bin') }
Check 'antigravity bin excluded' { (StatusOf 'antigravity-cli/bin') -eq 'skipped_excluded' }
Check 'codex packages excluded' { (StatusOf 'Users/alice/.codex/packages') -eq 'skipped_excluded' }
Check 'ollama model blobs excluded' { (StatusOf 'home/bob/.ollama/models/blobs') -eq 'skipped_excluded' }
Check 'ollama history collected (linux-style home in same image)' { (StatusOf 'home/bob/.ollama/history') -eq 'collected' }
Check 'bash history not collected' { -not ($script:Rows | Where-Object { $_.path -like '*.bash_history' }) }
Check 'PSReadLine history not collected' { -not ($script:Rows | Where-Object { $_.path -like '*ConsoleHost_history.txt' }) }
Check 'oversized file skipped_size' { (StatusOf 'Cursor/User/globalStorage/state.vscdb') -eq 'skipped_size' }
Check 'ms-python globalStorage excluded' { (StatusOf 'globalStorage/ms-python.python') -eq 'skipped_excluded' }
Check 'cline checkpoints excluded' { (StatusOf 'saoudrizwan.claude-dev/checkpoints') -eq 'skipped_excluded' }
Check 'weird filename collected' { (StatusOf 'weird name with spaces & [brackets].txt') -eq 'collected' }
if ($linkOk) {
  $r = Row 'antigravity-cli/cli.log'
  Check 'symlink recorded with target' { $r -and $r.type -eq 'symlink' -and $r.status -eq 'symlink' -and $r.target -like '*cli-1.log' }
}
Check 'project from history.jsonl (drive path mapped into image) collected' { (StatusOf 'proj/CLAUDE.md') -eq 'collected' }
Check 'project .claude settings collected' { (StatusOf 'proj/.claude/settings.local.json') -eq 'collected' }
Check 'project owner attributed' { (Row 'proj/CLAUDE.md').user -eq 'alice' }
# 2026-10-14 project files attributed to their agent (#104)
$r = Row 'proj/.claude/settings.local.json'
Check 'project .claude file attributed to claude-code' { $r -and ($r.home -replace '\\', '/').EndsWith('/proj') -and $r.agent -eq 'claude-code' -and $r.status -eq 'collected' }
$r = Row 'droid/AGENTS.md'
Check 'shared project AGENTS.md keeps agent project' { $r -and ($r.home -replace '\\', '/').EndsWith('/droid') -and $r.agent -eq 'project' -and $r.status -eq 'collected' }
Check 'project from workspace.json file URI collected' { (StatusOf 'Documents/app/.cursorrules') -eq 'collected' }
Check 'project from codex rollout cwd collected' { (StatusOf 'Documents/app/AGENTS.md') -eq 'collected' }
Check 'project from cline taskHistory collected' { (StatusOf 'cl/.clinerules') -eq 'collected' }
Check 'project from continue sessions.json collected' { (StatusOf 'cont/.continuerc.json') -eq 'collected' }
Check 'project from gemini projects.json collected' { (StatusOf 'gem/GEMINI.md') -eq 'collected' }
Check 'project-local crush.db from projects.json collected' { (StatusOf 'crushproj/.crush/crush.db') -eq 'collected' }
Check 'continue globalContext flagged secret' { (Row 'index/globalContext.json').secret -eq $true }
Check 'continue lancedb excluded' { (StatusOf 'index/lancedb') -eq 'skipped_excluded' }
Check 'cline providers.json flagged secret' { (Row 'settings/providers.json').secret -eq $true }
Check 'codex auth.json flagged secret' { (Row 'Users/alice/.codex/auth.json').secret -eq $true }
Check 'home .env not collected' { -not (Row 'Users/alice/.env') }
Check 'claude desktop config.json flagged secret' { (Row 'Roaming/Claude/config.json').secret -eq $true }
$r = Row 'Claude/claude_desktop_config.json'
Check 'factory session index not swallowed by cache exclusion' { (StatusOf 'Users/alice/.factory/cache/session-index/index.db') -eq 'collected' }
Check 'factory cache sounds excluded' { (StatusOf 'Users/alice/.factory/cache/sounds') -eq 'skipped_excluded' }
Check 'factory session cwd discovers project' { (StatusOf 'droid/AGENTS.md') -eq 'collected' }
$r2 = Row 'Users/alice/.kiro/powers/installed/p1/mcp.json'
Check 'kiro power mcp.json collected and flagged' { $r2 -and $r2.secret -eq $true -and $r2.status -eq 'collected' }
Check 'kiro cli session cwd discovers project' { (StatusOf 'kiroproj/.kiroignore') -eq 'collected' }
Check 'vscode-server User dir collected as vscode' { (Row 'Users/alice/.vscode-server/data/User/globalStorage/state.vscdb').agent -eq 'vscode' }
Check 'cline inside vscode-server attributed to cline' { (Row 'Users/alice/.vscode-server/data/User/globalStorage/saoudrizwan.claude-dev/state/taskHistory.json').agent -eq 'cline' }
Check 'vscode-server taskHistory discovers project' { (StatusOf 'remoteproj/.clinerules') -eq 'collected' }
Check 'antigravity-ide attributed to antigravity' { (Row 'Users/alice/.gemini/antigravity-ide/conversations/i1.db').agent -eq 'antigravity' }
Check 'antigravity history workspace discovers project' { (StatusOf 'agyproj/.antigravityignore') -eq 'collected' }
Check 'cursor auth.json flagged secret' { (Row 'Users/alice/.cursor/auth.json').secret -eq $true }
Check 'copilot pkg excluded' { (StatusOf 'Users/alice/.copilot/pkg') -eq 'skipped_excluded' }
Check 'copilot config.json flagged secret' { (Row 'Users/alice/.copilot/config.json').secret -eq $true }
Check 'copilot workspace.yaml cwd discovers project' { (StatusOf 'copproj/AGENTS.md') -eq 'collected' }
Check 'claude device keys flagged secret' { (Row 'Users/alice/.claude/.device-keys.json').secret -eq $true }
Check 'amp history cwd discovers project' { (StatusOf 'ampproj/.amp/settings.json') -eq 'collected' }
Check 'project-level kilo worktrees excluded' { (StatusOf 'kiloproj/.kilo/worktrees') -eq 'skipped_excluded' }
Check 'claude desktop mcp config flagged secret' { $r -and $r.secret -eq $true -and $r.status -eq 'collected' }
Check 'claude desktop Cache excluded' { (StatusOf 'Roaming/Claude/Cache') -eq 'skipped_excluded' }
# 1.4.0 catalog round (2026-10-04)
foreach ($c in $Cases14) {
  $f = @($c -split '\|', 3); $r = Row "alice/$($f[2])"
  switch ($f[0]) {
    'excl' { Check "excluded: $($f[2])" { $r -and $r.status -eq 'skipped_excluded' } }
    'exclf' { Check "excluded: $($f[2])" { $r -and $r.status -eq 'skipped_excluded' } }
    'secret' { Check "secret: $($f[2])" { $r -and $r.secret -eq $true -and $r.status -eq 'collected' } }
    'agent' { Check "$($f[1]): $($f[2])" { $r -and $r.agent -eq $f[1] -and $r.status -eq 'collected' } }
  }
}
# On a case-insensitive filesystem .config/PearAI/User matches the same directory and is collected once (#29)
$pr = @($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like '*/.config/pearai/User/globalStorage/state.vscdb' })
Check 'pearai lowercase .config/pearai collected as pearai' { $pr.Count -eq 1 -and @($pr | Where-Object { $_.agent -ne 'pearai' }).Count -eq 0 }
Check 'cody nested globalStorage collected exactly once' { @($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like '*sourcegraph.cody-ai/symf/indexroot/meta.json' }).Count -eq 1 }
Check 'twinny nested globalStorage collected exactly once' { @($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like '*globalStorage/rjmacarthy.twinny/twinny-providers.json' }).Count -eq 1 }
Check 'little-coder history nested in .pi collected exactly once' { @($script:Rows | Where-Object { $_.path -like '*little-coder-prompt-history.json' }).Count -eq 1 }
Check 'hermes installer checkout excluded but its .env kept' { (StatusOf 'alice/.hermes/hermes-agent/hermes_cli') -eq 'skipped_excluded' -and (StatusOf 'alice/.hermes/hermes-agent/.env') -eq 'collected' }
if ($clawLinkOk) {
  $r = Row 'home/bob/.clawdbot'
  Check 'openclaw .clawdbot rename symlink recorded' { $r -and $r.agent -eq 'openclaw' -and $r.type -eq 'symlink' -and $r.status -eq 'symlink' -and $r.target -like '*.openclaw' }
}
Check 'hermes checkpoint workdir discovers project' { (StatusOf 'hermesproj/.hermes.md') -eq 'collected' -and (Row 'hermesproj/.hermes.md').user -eq 'alice' }
Check 'letta sessions.jsonl project discovers project' { (StatusOf 'lettaproj/.letta/settings.json') -eq 'collected' }
Check 'project .letta/settings.json flagged secret (accepted overmatch)' { (Row 'lettaproj/.letta/settings.json').secret -eq $true }
Check 'letta local backend messages cwd discovers project' { (StatusOf 'lettaproj2/AGENTS.md') -eq 'collected' }
Check 'pi session cwd discovers project' { (StatusOf 'piproj/.pi/settings.json') -eq 'collected' }
Check 'pi misplaced session cwd discovers project' { (StatusOf 'piproj2/AGENTS.md') -eq 'collected' }
Check 'pi trust.json keys discover project' { (StatusOf 'pitrust/pi-session-2026-10-04.html') -eq 'collected' }
Check 'pi crashes.json cwd discovers project' { (StatusOf 'picrash/AGENTS.md') -eq 'collected' }
Check 'pi experimental meta cwd discovers project' { (StatusOf 'piexp/AGENTS.md') -eq 'collected' }
Check 'open-interpreter rollout cwd discovers project' { (StatusOf 'oiproj/.openinterpreter/rules/r.md') -eq 'collected' }
Check 'open-interpreter archived rollout cwd discovers project' { (StatusOf 'oiarch/.codewhale/notes.md') -eq 'collected' }
Check 'openhands workspaces.json path discovers project' { (StatusOf 'ohproj/.openhands/setup.sh') -eq 'collected' }
Check 'openhands canvas dev conversation discovers project' { (StatusOf 'ohdev/AGENTS.md') -eq 'collected' }
Check 'openhands canvas conversation discovers project' { (StatusOf 'ohcanvas/AGENTS.md') -eq 'collected' }
Check 'openhands cli base_state discovers project' { (StatusOf 'ohcli/AGENTS.md') -eq 'collected' }
Check 'pearai sessions.json discovers project' { (StatusOf 'pearproj/.pearairc.json') -eq 'collected' }
$r = Row 'pearproj/.pearai-agent/mcp.json'
Check 'project .pearai-agent/mcp.json flagged secret' { $r -and $r.secret -eq $true -and $r.status -eq 'collected' }
Check 'openclaw JSON5 workspace discovers project' { (StatusOf 'clawws/SOUL.md') -eq 'collected' }
Check 'openclaw JSON5 agentDir discovers project' { (StatusOf 'clawagent/AGENTS.md') -eq 'collected' }
Check 'openclaw legacy clawdbot.json discovers project' { (StatusOf 'clawlegacy/IDENTITY.md') -eq 'collected' }
Check 'openclaw profile config discovers project' { (StatusOf 'clawprofile/MEMORY.md') -eq 'collected' }
Check 'nanobot .workspace marker discovers project' { (StatusOf 'nanows/HEARTBEAT.md') -eq 'collected' }
Check 'nanobot instance config workspace discovers project' { (StatusOf 'nanocfg/memory/MEMORY.md') -eq 'collected' }
Check 'tabby config.toml file:// git_url (drive) discovers project' { (StatusOf 'tabbyproj/AGENTS.md') -eq 'collected' }
Check 'tabby config.toml file:// git_url (unix) discovers project' { (StatusOf 'srv/tabbyunix/AGENTS.md') -eq 'collected' }
Check 'twinny manifest common prefix discovers project' { (StatusOf 'twinproj/AGENTS.md') -eq 'collected' }
# 1.5.0 Docker volumes (2026-10-04)
$r = Row 'var/lib/docker/volumes/a0_usr/_data/chats/ctx1/chat.json'
Check 'docker volume file collected as agent-zero, user docker' { $r -and $r.user -eq 'docker' -and $r.agent -eq 'agent-zero' -and $r.status -eq 'collected' -and ($r.home -replace '\\', '/').EndsWith('var/lib/docker/volumes/a0_usr/_data') }
$r = Row 'var/lib/docker/volumes/a0_usr/_data/.env'
Check 'docker volume .env flagged secret (volume-relative)' { $r -and $r.secret -eq $true -and $r.status -eq 'collected' }
Check 'docker volume tmp/playwright excluded (volume-relative)' { (StatusOf 'var/lib/docker/volumes/a0_usr/_data/tmp/playwright') -eq 'skipped_excluded' }
$r = Row 'var/lib/docker/volumes/pgdata/_data'
Check 'unmatched volume recorded skipped_unmatched_volume with size' { $r -and $r.user -eq 'docker' -and $r.type -eq 'dir' -and $r.size -gt 0 -and $r.status -eq 'skipped_unmatched_volume' }
Check 'unmatched volume contents not collected' { $null -eq (Row 'pgdata/_data/x') }
Check 'volumes dir metadata.db not collected' { $null -eq (Row 'volumes/metadata.db') }
$r = Row 'Users/alice/.local/share/docker/volumes/tabby_data/_data/events/2026-10-01.json'
Check 'rootless volume collected as tabby' { $r -and $r.user -eq 'docker' -and $r.agent -eq 'tabby' -and $r.status -eq 'collected' }
# 2026-10-04 Muse Code
foreach ($c in $CasesMuse) {
  $f = @($c -split '\|', 3); $r = Row "alice/$($f[2])"
  switch ($f[0]) {
    'excl' { Check "excluded: $($f[2])" { $r -and $r.agent -eq 'muse-code' -and $r.status -eq 'skipped_excluded' } }
    'exclf' { Check "excluded: $($f[2])" { $r -and $r.agent -eq 'muse-code' -and $r.status -eq 'skipped_excluded' } }
    'secret' { Check "secret: $($f[2])" { $r -and $r.agent -eq 'muse-code' -and $r.secret -eq $true -and $r.status -eq 'collected' } }
    'agent' { Check "$($f[1]): $($f[2])" { $r -and $r.agent -eq $f[1] -and $r.status -eq 'collected' } }
  }
}
$r = Row 'alice/AppData/Local/Programs/muse/muse-bin-1.4.2-R1.exe'
Check 'muse windows binary excluded with its size' { $r -and $r.type -eq 'file' -and $r.size -eq 1 -and $r.status -eq 'skipped_excluded' }
Check 'muse .local/bin glob leaves other tools alone' { $null -eq (Row 'alice/.local/bin/othertool') }
Check 'muse trust.json projects key discovers project' { (StatusOf 'musetrust/AGENTS.md') -eq 'collected' -and (Row 'musetrust/AGENTS.md').user -eq 'alice' }
$r = Row 'museproj/.muse/hooks.json'
Check 'muse session.jsonl workspace_root discovers project' { $r -and $r.user -eq 'alice' -and $r.agent -eq 'muse-code' -and $r.status -eq 'collected' }
Check 'muse project .muse/worktrees excluded' { (StatusOf 'museproj/.muse/worktrees') -eq 'skipped_excluded' }
# 2026-10-04 relocated Claude Code home
$r = Row $CcwS
Check 'relocated claude home session collected as claude-code' { $r -and $r.agent -eq 'claude-code' -and $r.status -eq 'collected' }
$r = Row 'alice/.claude-work/history.jsonl'
Check 'relocated claude home history collected as claude-code' { $r -and $r.agent -eq 'claude-code' -and $r.status -eq 'collected' }
$r = Row 'alice/.claude-work/.credentials.json'
Check 'relocated claude home credentials flagged secret' { $r -and $r.agent -eq 'claude-code' -and $r.secret -eq $true -and $r.status -eq 'collected' }
$r = Row 'alice/.claude-work/.claude.json'
Check 'relocated claude home .claude.json flagged secret' { $r -and $r.agent -eq 'claude-code' -and $r.secret -eq $true -and $r.status -eq 'collected' }
# 2026-10-23 (#256)
$r = Row $CcwK; $r2 = Row 'alice/.claude-work/daemon/control.key'; $r3 = Row 'alice/.claude-work/daemon/roster.json'; $r4 = Row 'alice/.claude-work/backups/.claude.json.backup.1792800000000'
Check '#256 relocated claude home session key, daemon files and backup flagged secret' { $r -and $r2 -and $r3 -and $r4 -and @(@($r, $r2, $r3, $r4) | Where-Object { $_.agent -ne 'claude-code' -or $_.secret -ne $true -or $_.status -ne 'collected' }).Count -eq 0 }
Check 'claude-code-router not collected' { $null -eq (Row 'alice/.claude-code-router/config.json') }
$r = Row 'ccwork/.claude/settings.json'
Check 'relocated .claude.json projects key discovers project' { $r -and $r.user -eq 'alice' -and $r.agent -eq 'claude-code' -and $r.status -eq 'collected' }
$r = Row 'cchist/.claude/settings.json'
Check 'relocated history.jsonl discovers project' { $r -and $r.user -eq 'alice' -and $r.agent -eq 'claude-code' -and $r.status -eq 'collected' }
Check 'Public profile skipped' { $null -eq (Row 'Public/Desktop/readme.txt') }
Check 'Default profile skipped' { $null -eq (Row 'Default/NTUSER.DAT') }
$entries = ArchiveEntries
Check 'no live snapshot directory' { -not ($entries | Where-Object { $_ -match '(^|/)live/' }) }
Check 'manifest and summary inside archive' { ($entries | Where-Object { $_ -match 'manifest\.jsonl$' }) -and ($entries | Where-Object { $_ -match 'collection\.json$' }) }
Check 'archive layout is fs/<path relative to root>' { @($entries | Where-Object { $_ -match '(^|\./)fs/Users/alice/\.claude/history\.jsonl$' }).Count -eq 1 }
Check 'staging removed' { -not (Get-ChildItem -LiteralPath (Join-Path $Out 'default') -Filter '.stage-*' -Force) }
$sum = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json
Check 'summary is valid JSON with zero copy errors' { $sum.counts.error_copy -eq 0 }
Check 'summary has no no_live option' { $null -eq $sum.options.PSObject.Properties['no_live'] }
Check 'summary counts match manifest' { $sum.counts.collected -eq @($script:Rows | Where-Object { $_.status -eq 'collected' }).Count }
Check 'manifest rows all parsed as JSON' { $script:Rows.Count -eq @(Get-Content -LiteralPath $script:M.FullName).Count }
Check 'archive layout for a docker volume file is fs/<path relative to root>' { @($entries | Where-Object { $_ -match '(^|\./)fs/var/lib/docker/volumes/a0_usr/_data/chats/ctx1/chat\.json$' }).Count -eq 1 }
Check 'summary counts skipped_unmatched_volume' { $sum.counts.skipped_unmatched_volume -eq 1 }
Check 'summary docker counts' { $sum.docker.volumes_found -eq 3 -and $sum.docker.volumes_collected -eq 2 -and $sum.docker.unreadable -eq 0 -and $sum.docker.docker_desktop -eq $false }
Check 'summary no_docker option false and notes empty' { $sum.options.no_docker -eq $false -and @($sum.notes).Count -eq 0 }
Check 'stdout docker line' { $script:stdout -match '(?m)^docker:     3 volumes found, 2 collected, 0 unreadable\s*$' }
Check 'profile without artifacts still listed in users' { @($sum.users) -contains 'dave' }
Check 'profile without artifacts not in users_with_artifacts' { @($sum.users_with_artifacts).Count -gt 0 -and -not (@($sum.users_with_artifacts) -contains 'dave') }
Check 'stdout users counts users_with_artifacts' { $script:stdout -match "(?m)^users:      $(@($sum.users_with_artifacts).Count)\s*$" }
Check 'log has no progress line for a profile without artifacts' { $lg = Get-Content -LiteralPath (Get-ChildItem -LiteralPath (Join-Path $Out 'default') -Filter '*.log' | Select-Object -First 1).FullName -Raw; $lg -notmatch 'User dave' -and $lg -match 'User alice' }
Check 'stdout size is human-readable' { $script:stdout -match '(?m)^size:       \d+ \([0-9.]+ (B|KiB|MiB)\)\s*$' }
Check 'stdout collected bytes are human-readable' { $script:stdout -match '(?m)^collected:  \d+ files, \d+ bytes \([0-9.]+ (B|KiB|MiB)\)\s*$' }

# 2026-10-04 bug round: #29
function CountOf([string]$name) { return @($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like "*/$name" }).Count }
function HasPath([string]$rel) { $w = (P $rel); return @($script:Rows | Where-Object { $_.path -ceq $w -and $_.status -eq 'collected' }).Count -eq 1 }
$log29 = Get-Content -LiteralPath (Get-ChildItem -LiteralPath (Join-Path $Out 'default') -Filter '*.log' | Select-Object -First 1).FullName -Raw
if ($caseInsensitive) {
  Write-Output "note: $Work is case-insensitive; checking the folded layout"
  Check '#29 case variants of one directory collected once' { (CountOf 'case29-upper.json') -eq 1 -and (CountOf 'case29-lower.json') -eq 1 }
  # PowerShell records the on-disk spelling (the CASES14 block above created .config/pearai first)
  Check '#29 path recorded in its on-disk spelling' { (HasPath 'Users/alice/.config/pearai/User/case29-upper.json') -and (HasPath 'Users/alice/.config/pearai/User/case29-lower.json') }
  Check '#29 nested case variant collected once under the nested entry' { (CountOf 'case29-editor.json') -eq 1 -and (HasPath 'Users/alice/.config/cursor/User/case29-editor.json') }
  # 5.1 wraps long log lines written through a redirected console, so whitespace is folded first
  Check '#29 dropped variant logged' { ($log29 -replace '\s+', ' ') -match '\[pearai\] \S*\.config[\\/]pearai[\\/]User: catalog line \.config/pearai/User names the same path as an earlier line \(case-insensitive filesystem\)' }
} else {
  Check '#29 PearAI and pearai are distinct here and both collected' { (HasPath 'Users/alice/.config/PearAI/User/case29-upper.json') -and (HasPath 'Users/alice/.config/pearai/User/case29-lower.json') -and (CountOf 'case29-upper.json') -eq 1 -and (CountOf 'case29-lower.json') -eq 1 }
  Check '#29 nested Cursor/User distinct from cursor and both collected' { (HasPath 'Users/alice/.config/cursor/case29-cli.json') -and (HasPath 'Users/alice/.config/Cursor/User/case29-editor.json') -and (CountOf 'case29-editor.json') -eq 1 -and (Row 'alice/.config/Cursor/User/case29-editor.json').agent -eq 'cursor' }
  Check '#29 nothing folded on a case-sensitive filesystem' { $log29 -notmatch 'case-insensitive filesystem' }
}

# 2026-10-06 Ollama (#44)
$r = Row $olm
Check 'ollama model manifest collected' { $r -and $r.agent -eq 'ollama' -and $r.status -eq 'collected' }
Check 'ollama blob not collected' { $null -eq (Row 'blobs/sha256-abc') }

# 2026-10-06 frameworks sweep (#64)
foreach ($c in $CasesFw) {
  $f = @($c -split '\|', 3); $r = Row "alice/$($f[2])"
  switch ($f[0]) {
    'excl' { Check "excluded: $($f[2])" { $r -and $r.status -eq 'skipped_excluded' } }
    'exclf' { Check "excluded: $($f[2])" { $r -and $r.status -eq 'skipped_excluded' } }
    'secret' { Check "secret: $($f[2])" { $r -and $r.secret -eq $true -and $r.status -eq 'collected' } }
    'agent' { Check "$($f[1]): $($f[2])" { $r -and $r.agent -eq $f[1] -and $r.status -eq 'collected' } }
  }
}
Check 'crewai mid-path wildcard leaves other files in the project dir alone' { $null -eq (Row 'alice/.local/share/myproj/unrelated.txt') }
$r = Row 'home/bob/AppData/Local/crewai/myproj/latest_kickoff_task_outputs.db'
Check 'crewai lowercase AppData/Local/crewai collected through the class' { $r -and $r.agent -eq 'crewai' -and $r.status -eq 'collected' }
$r = Row 'home/bob/AppData/Local/crewai/credentials/tokens.enc'
Check 'crewai lowercase credentials flagged secret through the class' { $r -and $r.secret -eq $true -and $r.status -eq 'collected' }
Check 'camel-ai narrow lines leave Apache Camel JBang files alone' { $null -eq (Row 'alice/.camel/4242-status.json') }
Check 'legacy open-interpreter space-named dir collected once' { (CountOf 'Open Interpreter Terminal/conversations/old.json') -eq 1 }

# 2026-10-11 Claude Desktop Linux deb and Claude Code 2.1.295 session keys (#73, #76)
function Is76([string]$rel, [string]$agent, [bool]$secret) { $r = Row $rel; return ($r -and $r.agent -eq $agent -and $r.secret -eq $secret -and $r.status -eq 'collected') }
Check '#73 Linux spaces-present link-key flagged secret' { Is76 $l76 'claude-desktop' $true }
Check '#76 Claude Code sessions/<pid>.<hash>.key flagged secret' { Is76 $k76 'claude-code' $true }
Check '#76 Claude Code sessions/<pid>.json collected, not secret' { Is76 'Users/alice/.claude/sessions/4242.json' 'claude-code' $false }
Check '#73 Linux git-shadow/cli-temp-roots.json collected as claude-desktop' { Is76 "$c76/git-shadow/cli-temp-roots.json" 'claude-desktop' $false }
Check '#73 Linux logs/main.log inside the data dir collected as claude-desktop' { Is76 "$c76/logs/main.log" 'claude-desktop' $false }
Check '#73 Linux Code-tab session record collected as claude-desktop' { Is76 $s76 'claude-desktop' $false }
Check '#73 Linux claude-code excluded, downloaded CLI not in the manifest' { (StatusOf "$c76/claude-code") -eq 'skipped_excluded' -and @($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like '*/9b32b47ec4b3/*' }).Count -eq 0 }

# 2026-10-11 Claude Code CLI cache directory (#81)
$r = Row $f81
Check '#81 Claude Code CLI cache MCP log collected as claude-code' { $r -and $r.agent -eq 'claude-code' -and $r.status -eq 'collected' }
Check '#81 Claude Code CLI cache MCP log not secret' { $r -and $r.secret -eq $false -and $r.status -eq 'collected' }
$r = Row $w81
Check '#81 Claude Code CLI cache Windows Cache child collected as claude-code' { $r -and $r.agent -eq 'claude-code' -and $r.status -eq 'collected' }

# 2026-10-13 Antigravity desktop app (#83, #84)
function Is83([string]$rel, [bool]$secret) { $r = Row $rel; return ($r -and $r.agent -eq 'antigravity' -and $r.secret -eq $secret -and $r.status -eq 'collected') }
function NoRow83([string]$tail) { return (@($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like "*/$tail" }).Count -eq 0) }
Check '#83 Antigravity app conversation collected as antigravity' { Is83 "$g83/conversations/a1.db" $false }
Check '#83 Antigravity app crashes/ collected' { (StatusOf "$g83/crashes/crash_1.log") -eq 'collected' }
Check '#84 Antigravity plugin token.json flagged secret' { Is83 "$g83/plugin_data/gdocs/token.json" $true }
Check '#83 Antigravity plugin binary excluded' { (StatusOf "$g83/plugin_data/gdocs/bin") -eq 'skipped_excluded' -and (NoRow83 'gdocs/bin/gdocs-1') }
Check '#83 Antigravity app bin excluded' { (StatusOf "$g83/bin") -eq 'skipped_excluded' -and (NoRow83 '.gemini/antigravity/bin/webm_encoder') }
Check '#83 Antigravity marketplace cache excluded, other cache files collected' { (StatusOf "$g83/cache/marketplaces") -eq 'skipped_excluded' -and (StatusOf "$g83/cache/last_conversations.json") -eq 'collected' }
Check '#83 Antigravity Electron app_storage.json collected as antigravity' { Is83 "$e83/app_storage.json" $false }
Check '#83 Antigravity Electron Cache and Code Cache excluded' { (StatusOf "$e83/Cache") -eq 'skipped_excluded' -and (StatusOf "$e83/Code Cache") -eq 'skipped_excluded' -and (NoRow83 'Application Support/Antigravity/Cache/data_0') -and (NoRow83 'Antigravity/Code Cache/js/x') }
Check '#83 Antigravity Library/Logs main.log collected as antigravity' { Is83 'Users/alice/Library/Logs/Antigravity/main.log' $false }
Check '#83 Antigravity Windows app_storage.json collected as antigravity' { Is83 "$w83/app_storage.json" $false }
Check '#83 Antigravity Windows Electron Cache excluded' { (StatusOf "$w83/Cache") -eq 'skipped_excluded' -and (NoRow83 'Roaming/Antigravity/Cache/data_0') }
Check '#83 Antigravity data dir cache/ not pruned by the Electron Cache exclusion' { (StatusOf "$g83/cache/last_conversations.json") -eq 'collected' -and (StatusOf "$g83/cache") -ne 'skipped_excluded' }

# 2026-10-13 Antigravity Linux round (#83, #90, #91)
Check '#90 Antigravity CLI plugin-secrets.json flagged secret' { Is83 "$w83/plugin-secrets.json" $true }
Check '#90 Antigravity CLI plugin-secrets.json collected once' { (CountOf 'plugin-secrets.json') -eq 1 }
Check '#83 Antigravity Electron Dictionaries excluded' { (StatusOf "$w83/Dictionaries") -eq 'skipped_excluded' -and (NoRow83 'Dictionaries/en-US-10-1.bdic') }
Check '#83 Antigravity app sidecar SDK under lib/node_modules excluded' { (StatusOf "$g83/lib/node_modules") -eq 'skipped_excluded' -and (NoRow83 'antigravity/lib/node_modules/sidecar_sdk/index.mjs') }
Check '#83 Antigravity config/node_modules excluded' { (StatusOf 'Users/alice/.gemini/config/node_modules') -eq 'skipped_excluded' -and (NoRow83 'config/node_modules/sidecar_sdk/index.mjs') }
Check '#91 Antigravity project folderUri discovers project' { (StatusOf 'agyapp/.antigravityignore') -eq 'collected' }
Check '#91 Antigravity drive-letter folderUri discovers project' { (StatusOf 'agywin/.antigravityignore') -eq 'collected' }
# 2026-10-14 catalog match that is an excluded file (#107)
$r107 = Row 'Users/alice/.local/bin/.muse-update.107.exe'
Check '#107 excluded file match gets a skipped_excluded row with its size' { $r107 -and $r107.user -eq 'alice' -and $r107.home -eq (P 'Users/alice') -and $r107.agent -eq 'muse-code' -and $r107.archive_path -eq '' -and $r107.type -eq 'file' -and $r107.size -eq 5 -and $r107.sha256 -eq '' -and $r107.secret -eq $false -and $r107.status -eq 'skipped_excluded' -and $r107.target -eq '' -and $r107.error -eq '' }
Check '#107 excluded file match not archived' { -not ($DefaultEntries | Where-Object { $_ -like '*muse-update.107.exe' }) }
# 2026-10-14 Antigravity on Windows (#83)
Check '#83 Antigravity Windows staging file collected as antigravity' { Is83 "$l83/antigravity/staging/s1" $false }
Check '#83 Antigravity installer and program directory not collected' { (NoRow83 'antigravity-updater/installer.exe') -and (NoRow83 'Programs/antigravity/Antigravity.exe') }
# 2026-10-15 ChatGPT desktop as the OpenAI.Codex package (#113)
function Is113([string]$rel, [string]$agent, [bool]$secret) { $r = Row $rel; return ($r -and $r.agent -eq $agent -and $r.secret -eq $secret -and $r.status -eq 'collected') }
Check '#113 ChatGPT profile Local Storage collected as chatgpt-desktop' { Is113 "$c113/Default/Local Storage/leveldb/000003.log" 'chatgpt-desktop' $false }
Check '#113 ChatGPT Local State flagged secret' { Is113 "$c113/Local State" 'chatgpt-desktop' $true }
Check '#113 ChatGPT profile and partition cookies flagged secret' { (Is113 "$c113/Default/Network/Cookies" 'chatgpt-desktop' $true) -and (Is113 "$x113/Network/Cookies" 'chatgpt-desktop' $true) }
Check '#113 ChatGPT Login Data flagged secret' { Is113 "$c113/Default/Login Data" 'chatgpt-desktop' $true }
Check '#113 ChatGPT profile and partition Cache excluded' { (StatusOf "$c113/Default/Cache") -eq 'skipped_excluded' -and (StatusOf "$x113/Cache") -eq 'skipped_excluded' -and (NoRow83 'Cache/data_0') }
Check '#113 ChatGPT component cache beside the profile not in the manifest' { -not ($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like '*/web/Codex/component_crx_cache*' }) }
Check '#113 ChatGPT app log collected as chatgpt-desktop' { Is113 "$p113/LocalCache/Local/Codex/Logs/2026/10/15/codex-desktop-x.log" 'chatgpt-desktop' $false }
Check '#113 ChatGPT MSIX settings hive collected' { Is113 "$p113/Settings/settings.dat" 'chatgpt-desktop' $false }
Check '#116 Codex plugin app-server binaries excluded' { (StatusOf 'Users/alice/.codex/plugins/.plugin-appserver') -eq 'skipped_excluded' -and (NoRow83 '.plugin-appserver/codex.exe') }
Check '#115 Codex desktop global state flagged secret' { Is113 'Users/alice/.codex/.codex-global-state.json' 'codex-cli' $true }
# 2026-10-15 ChatGPT desktop on macOS (#121)
Check '#121 ChatGPT macOS Local Storage collected as chatgpt-desktop' { Is113 "$m121/Default/Local Storage/leveldb/000003.log" 'chatgpt-desktop' $false }
Check '#121 ChatGPT macOS profile and partition cookies flagged secret' { (Is113 "$m121/Default/Cookies" 'chatgpt-desktop' $true) -and (Is113 "$x121/Cookies" 'chatgpt-desktop' $true) }
Check '#121 ChatGPT macOS Login Data flagged secret' { Is113 "$m121/Default/Login Data" 'chatgpt-desktop' $true }
Check '#121 ChatGPT macOS profile and partition Cache excluded' { (StatusOf "$m121/Default/Cache") -eq 'skipped_excluded' -and (StatusOf "$x121/Cache") -eq 'skipped_excluded' -and (NoRow83 'Codex/Default/Cache/data_0') -and (NoRow83 'codex-browser-app/Cache/data_0') }
Check '#121 ChatGPT macOS MCP server script excluded, manifest collected' { (StatusOf "$m121/executor-plugins/codex-app-tools/server.mjs") -eq 'skipped_excluded' -and (Is113 "$m121/executor-plugins/codex-app-tools/.mcp.json" 'chatgpt-desktop' $false) }
Check '#121 ChatGPT macOS component cache not in the manifest' { -not ($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like '*Application Support/Codex/component_crx_cache*' }) }
Check '#121 ChatGPT macOS app log collected as chatgpt-desktop' { Is113 'Users/alice/Library/Logs/com.openai.codex/2026/10/15/codex-desktop-x.log' 'chatgpt-desktop' $false }
Check '#121 ChatGPT macOS preferences collected' { Is113 'Users/alice/Library/Preferences/com.openai.codex.plist' 'chatgpt-desktop' $false }
Check '#121 ChatGPT macOS binary cookies flagged secret' { Is113 'Users/alice/Library/HTTPStorages/com.openai.codex.binarycookies' 'chatgpt-desktop' $true }
Check '#121 ChatGPT computer-use group container collected' { Is113 "$g121/IPC/computeruse.sock.lock" 'chatgpt-desktop' $false }
Check '#121 Codex computer-use app bundle excluded, config collected' { (StatusOf "$u121/Codex Computer Use.app") -eq 'skipped_excluded' -and (NoRow83 'Computer Use.app/Contents/Info.plist') -and (Is113 "$u121/config.json" 'codex-cli' $false) }
# 2026-10-15 special files (#120)
$n120 = 0
if ($sock120) {
  $n120 = 1
  $type120 = 'socket'; if ($env:OS -eq 'Windows_NT') { $type120 = 'other' }
  $r = Row $sock120Rel
  Check '#120 socket recorded as skipped_special, not copied' { $r -and $r.archive_path -eq '' -and $r.type -eq $type120 -and $r.sha256 -eq '' -and $r.secret -eq $false -and $r.status -eq 'skipped_special' -and $r.target -eq '' -and $r.error -eq '' }
  $sock120.Close()
}
Check '#120 special files not in the archive' { -not (ArchiveEntries | Where-Object { $_ -like '*ipc.fifo' -or $_ -like '*daemon-updater.sock' }) }
Check '#120 summary counts skipped_special' { $sum.counts.skipped_special -eq $n120 }
Check '#120 stdout skipped line counts special files' { $script:stdout -match "(?m)^skipped:    \d+ excluded, \d+ too large, \d+ secret, $n120 special\s*$" }
Check '#120 no symlink row targets its own path' { -not ($script:Rows | Where-Object { $_.status -eq 'symlink' -and ($_.target -replace '^\\\\\?\\', '' -replace '[\\/]+', '/') -eq ($_.path -replace '[\\/]+', '/') }) }

# 2026-10-16 GitHub Copilot Desktop (#147)
Check '#147 Copilot Desktop data.db collected as copilot-desktop' { (Is113 "$d147/data.db" 'copilot-desktop' $false) -and (Is113 "$d147/data.db-wal" 'copilot-desktop' $false) }
Check '#147 Copilot Desktop github-app log collected as copilot-desktop' { Is113 "$d147/logs/github-app.1.log" 'copilot-desktop' $false }
Check '#147 Copilot Desktop localstorage collected as copilot-desktop' { Is113 "$l147/localstorage/tauri_localhost_0.localstorage" 'copilot-desktop' $false }
Check '#147 Foundry Local log collected as copilot-desktop' { Is113 'Users/alice/.github-copilot-cli/logs/foundry.core20261016.log' 'copilot-desktop' $false }
Check '#147 Copilot Desktop session workspace.yaml stays copilot-cli' { Is113 "$d147/session-state/s2/workspace.yaml" 'copilot-cli' $false }
Check '#147 Copilot Desktop ws.token flagged secret' { Is113 "$d147/run/ws.token" 'copilot-desktop' $true }
Check '#147 Copilot Desktop checkpoint ref and HEAD collected as copilot-desktop' { (Is113 "$c147/e0000000-0000-4000-8000-000000000020" 'copilot-desktop' $false) -and (Is113 "$r147/HEAD" 'copilot-desktop' $false) }
Check '#147 Copilot Desktop repos working tree, worktrees, objects and index excluded' { (StatusOf "$d147/repos") -eq 'skipped_excluded' -and (StatusOf "$r147/objects") -eq 'skipped_excluded' -and (StatusOf "$r147/index") -eq 'skipped_excluded' -and $null -eq (Row 'repos/proj/README.md') -and $null -eq (Row 'alice-x/AGENTS.md') -and $null -eq (Row 'ab/cdef0123') }
Check '#147 Copilot Desktop app-skills excluded' { (StatusOf "$l147/app-skills") -eq 'skipped_excluded' -and $null -eq (Row 'app-skills/af/SKILL.md') }
$log147 = Get-Content -LiteralPath (Get-ChildItem -LiteralPath (Join-Path $Out 'default') -Filter '*.log' | Select-Object -First 1).FullName -Raw
$home147 = (P $d147) + $Sep
Check '#147 Copilot Desktop chat directory and worktree not projects' { $log147 -notmatch 'Project .*[\\/]\.copilot[\\/]' -and -not ($script:Rows | Where-Object { $_.home.StartsWith($home147) }) -and -not (@($sum.projects) | Where-Object { $_ -match '\.copilot[\\/](chats|repos)' }) }
Check '#147 Copilot Desktop chat directory file collected once as copilot-desktop' { @($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like '*/x-5d404e14/.keep' }).Count -eq 1 -and (Row "$d147/chats/2026-10-16/x-5d404e14/.keep").agent -eq 'copilot-desktop' }
# 2026-10-17 Copilot Desktop Windows round (#147)
Check '#147 WebView2 Local Storage collected as copilot-desktop' { Is113 "$w147/Default/Local Storage/leveldb/000003.log" 'copilot-desktop' $false }
Check '#147 WebView2 cookies and Local State flagged secret' { (Is113 "$w147/Default/Network/Cookies" 'copilot-desktop' $true) -and (Is113 "$w147/Local State" 'copilot-desktop' $true) }
Check '#147 WebView2 Cache and component_crx_cache excluded' { (StatusOf "$w147/Default/Cache") -eq 'skipped_excluded' -and (StatusOf "$w147/component_crx_cache") -eq 'skipped_excluded' -and $null -eq (Row 'Cache_Data/x') -and $null -eq (Row 'component_crx_cache/x') }
Check '#147 Copilot Desktop chat project collected less node_modules' { (Is113 "$p147/package.json" 'copilot-desktop' $false) -and (StatusOf "$p147/node_modules") -eq 'skipped_excluded' -and $null -eq (Row 'node_modules/m/index.js') }
Check '#131 Copilot CLI marketplaces excluded' { (StatusOf $k147) -eq 'skipped_excluded' -and $null -eq (Row 'marketplaces/m/.git/HEAD') }
Check '#147 Copilot pool session cwd not a project' { (StatusOf 'coppool/AGENTS.md') -eq '' -and -not (@($sum.projects) | Where-Object { $_ -match 'coppool' }) }
# 2026-10-17 session sync round (#153)
Check '#153 nanobot remote pairing identity and exchange keys flagged secret' { (Is113 "$n153/identity" 'nanobot' $true) -and (Is113 "$n153/exchange" 'nanobot' $true) -and (Is113 "$n153/request" 'nanobot' $false) }
Check '#153 Agent Zero plugin config.json flagged secret' { (Is113 "Users/alice/agent-zero/main/usr/$t153" 'agent-zero' $true) -and (Is113 "Users/alice/Desktop/agent-zero/usr/$t153" 'agent-zero' $true) }
Check '#153 Agent Zero volume plugin config.json flagged secret' { (Is113 "$v153/$t153" 'agent-zero' $true) -and (Row "$v153/$t153").user -eq 'docker' -and (Is113 "$v153/usr/$t153" 'agent-zero' $true) }
Check '#153 Cline cached remote config flagged secret' { Is113 "$g153/remote_config_org1.json" 'cline' $true }
Check '#153 Cline globalStorage cache collected' { (Is113 "$g153/sync-queue.json" 'cline' $false) -and (StatusOf $g153) -eq '' }
Check '#153 Cline webhook_config.json flagged secret' { Is113 'Users/alice/Documents/Cline/webhook_config.json' 'cline' $true }
Check '#153 Gemini CLI bug-memory heap snapshot flagged secret' { Is113 'Users/alice/.gemini/tmp/gem/bug-memory-1792000000000.heapsnapshot' 'gemini-cli' $true }
Check '#153 little-coder legacy config.json flagged secret' { Is113 'Users/alice/.little-coder/config.json' 'little-coder' $true }
Check '#153 Qwen Code channel credentials flagged secret' { (Is113 'Users/alice/.qwen/channels/qqbot-credentials.json' 'qwen-code' $true) -and (Is113 'Users/alice/.qwen/channels/weixin/account.json' 'qwen-code' $true) }
Check '#153 Qwen Code channel routing files not flagged' { (Is113 'Users/alice/.qwen/channels/sessions.json' 'qwen-code' $false) -and (Is113 'Users/alice/.qwen/channels/daemon/0123abcd/routes.json' 'qwen-code' $false) }
Check '#153 Kilo log directory collected' { Is113 'Users/alice/.local/share/kilo/log/2026-10-17T120000.log' 'kilo-code' $false }
# 2026-10-18 Codex shell snapshots (#160)
Check '#160 Codex shell snapshot flagged secret' { Is113 $s160 'codex-cli' $true }
# 2026-10-19 Codex projectless output directories (#149)
Check '#149 Codex projectless output collected' { (Is113 "$w149/outputs/report.md" 'codex-cli' $false) -and ((Row "$w149/outputs/report.md").home -replace '\\', '/') -like '*/home/bob' }
Check '#149 Codex projectless dir not a project' { -not (@($sum.projects) | Where-Object { $_ -match 'Documents[\\/]Codex' }) -and -not ($script:Rows | Where-Object { $_.home -match 'Documents[\\/]Codex' }) -and $log147 -notmatch 'Project .*Documents[\\/]Codex' }
Check '#149 Codex rollout cwd still a project' { @($sum.projects | Where-Object { ($_ -replace '\\', '/') -like '*/Users/alice/Documents/app' }).Count -eq 1 }

# 2026-10-20 Cursor IDE round on macOS (#6)
function Is6([string]$rel) { $r = Row $rel; return ($r -and $r.agent -eq 'cursor' -and $r.status -eq 'collected') }
function NoRow6([string]$tail) { return (@($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like "*/$tail" }).Count -eq 0) }
Check '#6 Cursor AgentStores sync index collected' { Is6 "$c6/AgentStores/cursor_agent_stores/u1/.sync/index.sqlite" }
Check '#6 Cursor AgentStores pin collected' { Is6 "$c6/AgentStores/cursor_agent_stores/.control/u1/pins/1-x.json" }
Check '#6 Cursor update-supervisor events collected' { Is6 "$u6/events.jsonl" }
Check '#6 Cursor update-supervisor binary excluded' { (StatusOf "$u6/cursor-update-supervisor") -eq 'skipped_excluded' }
Check '#6 Cursor embedded agent CLI excluded' { (StatusOf "$w6/agent-cli") -eq 'skipped_excluded' -and (NoRow6 'agent-cli/.local/share/x') }
Check '#6 Cursor agent worker log collected' { Is6 "$w6/cursor-agent-worker-1.log" }
Check '#6 Cursor canvases node_modules excluded' { (StatusOf 'Users/alice/.cursor/projects/p/canvases/node_modules') -eq 'skipped_excluded' -and (NoRow6 'node_modules/x.d.ts') }
Check '#6 Cursor agent transcript collected' { Is6 'Users/alice/.cursor/projects/p/agent-transcripts/u/u.jsonl' }
Check '#6 Cursor statsig cache excluded' { (StatusOf 'Users/alice/.cursor/statsig-cache.json') -eq 'skipped_excluded' }

# 2026-10-20 Cursor IDE round on Ubuntu (#236)
Check '#236 Cursor Linux agent-stores collected' { (Is6 "$l236/u1/.sync/index.sqlite") -and (Is6 "$l236/.control/u1/pins/1-x.json") }

# 2026-10-21 Cursor IDE round on Windows (#236)
Check '#236 Cursor Windows agent-stores collected' { (Is6 "$s236/u1/.sync/index.sqlite") -and (Is6 "$s236/.control/u1/pins/1-x.json") }
Check '#236 Cursor Windows embedded agent CLI excluded' { (StatusOf "$w236/agent-cli") -eq 'skipped_excluded' -and (NoRow6 'anysphere.cursor-agent-worker/agent-cli/x') }
Check '#236 Cursor Windows agent worker log collected' { Is6 "$w236/cursor-agent-worker-1.log" }
Check '#236 Cursor plugin cache excluded' { (StatusOf "$p236/cache") -eq 'skipped_excluded' -and (NoRow6 'cache/cursor-public/x/0123abcd/mcp.json') }
Check '#236 Cursor local plugins collected' { Is6 "$p236/local/x.json" }
Check '#236 Cursor Windows inno updater excluded' { (StatusOf "$u236/inno_updater.exe") -eq 'skipped_excluded' }
Check '#236 Cursor Windows update-supervisor state collected' { (Is6 "$u236/app-ready.json") -and (Is6 "$u236/state.json") }
# 2026-10-21 OpenHands Agent Canvas credentials and workspaces (#218)
Check '#218 OpenHands Agent Canvas mars-credentials.json flagged secret' {
  @($m218 | Where-Object {
      $r = Row $_
      -not ($r -and $r.agent -eq 'openhands' -and $r.secret -eq $true -and $r.status -eq 'collected')
    }).Count -eq 0
}
Check '#218 OpenHands automation workspaces excluded' { (StatusOf 'Users/alice/.openhands/workspaces') -eq 'skipped_excluded' -and -not (Row 'Users/alice/.openhands/workspaces/run1/f') }
Check '#218 OpenHands workspaces.json beside the excluded workspaces collected' { (StatusOf 'Users/alice/.openhands/workspaces.json') -eq 'collected' }

# 2026-10-21 Agent Zero source review (#217)
Check '#217 Agent Zero WhatsApp session flagged secret' { (Is113 "Users/alice/agent-zero/main/$w217" 'agent-zero' $true) -and (Is113 "Users/alice/Desktop/agent-zero/$w217" 'agent-zero' $true) -and (Is113 "var/lib/docker/volumes/a0_usr/_data/$w217" 'agent-zero' $true) -and (Row "var/lib/docker/volumes/a0_usr/_data/$w217").user -eq 'docker' }
Check '#217 Agent Zero ACP workspace and extra folder discovered' { (StatusOf 'srv/a0acp/AGENTS.md') -eq 'collected' -and (StatusOf 'srv/a0extra/AGENTS.md') -eq 'collected' }
Check '#217 Agent Zero connector screen capture collected' { Is113 $t217 'agent-zero' $false }

# 2026-10-21 framework catalog gaps (#223, #224, #225)
$r = Row 'proj/.crewai/last_run.json'
Check '#223 CrewAI project .crewai collected' { $r -and ($r.home -replace '\\', '/').EndsWith('/proj') -and $r.agent -eq 'crewai' -and $r.status -eq 'collected' }
function IsSecret224([string]$rel) { $r = Row $rel; return ($r -and $r.secret -eq $true -and $r.status -eq 'collected') }
Check '#224 difyctl login-pending.yml flagged secret' { (IsSecret224 'Users/alice/.config/difyctl/login-pending.yml') -and (IsSecret224 'Users/alice/AppData/Roaming/difyctl/login-pending.yml') -and (IsSecret224 'Users/alice/AppData/Local/difyctl/login-pending.yml') }
function Is225([string]$rel) { $r = Row $rel; return ($r -and $r.agent -eq 'pydantic-clai' -and $r.status -eq 'collected') }
Check '#225 CLAI 2.0 state directory collected' { (Is225 "$p225/orchestrator.json") -and (Is225 "$p225/workspaces/registry/ws1/workspace.json") -and (Is225 "$p225/workspaces/registry/ws1/session.log") }
Check '#225 CLAI 2.0 workspace token flagged secret' { (Is225 "$p225/workspaces/registry/ws1/token") -and (Row "$p225/workspaces/registry/ws1/token").secret -eq $true }
Check '#225 CLAI 2.0 workspace clones excluded' { (StatusOf "$p225/workspaces/clones") -eq 'skipped_excluded' -and @($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like '*/repo-0123456789/.git/HEAD' }).Count -eq 0 }

# 2026-10-21 Codex worktree cwds and archived threads (#222)
Check '#222 Codex archived rollout cwd discovers project' { (StatusOf 'codexarch/AGENTS.md') -eq 'collected' -and @($sum.projects | Where-Object { ($_ -replace '\\', '/') -like '*/codexarch' }).Count -eq 1 }
Check '#222 Codex worktree cwd not a project' { -not (@($sum.projects) | Where-Object { $_ -match '\.codex[\\/]worktrees' }) -and (StatusOf 'home/bob/.codex/worktrees') -eq 'skipped_excluded' -and -not ($script:Rows | Where-Object { $_.path -match 'worktrees[\\/]a1b2[\\/]repo[\\/]AGENTS\.md' }) }
Check '#222 Open Interpreter worktree cwd not a project' { -not (@($sum.projects) | Where-Object { $_ -match '\.openinterpreter[\\/]worktrees' }) -and -not ($script:Rows | Where-Object { $_.path -match 'worktrees[\\/]c3d4[\\/]repo[\\/]AGENTS\.md' }) }

# 2026-10-21 Cody JetBrains plugin files (#214)
Check '#214 Cody JetBrains options files collected' { (Is113 "$o214/cody.xml" 'cody' $true) -and (Is113 "$o214/cody_application_settings.xml" 'cody' $false) }
Check '#214 Cody cody_accounts.xml flagged secret' { Is113 "$o214/cody_accounts.xml" 'cody' $true }
Check '#214 Cody cody_accounts_settings.xml not flagged' { Is113 "$o214/cody_accounts_settings.xml" 'cody' $false }
Check '#214 Cody home .sourcegraph collected' { Is113 'Users/alice/.sourcegraph/cody_settings.json' 'cody' $true }
Check '#214 Cody project .idea files collected' { (Is113 'proj/.idea/cody_history.xml' 'cody' $false) -and (Is113 'proj/.idea/.sourcegraph/cody_settings.json' 'cody' $true) }

# 2026-10-21 agent worktrees inside a project (#216)
Check '#216 Gemini CLI and Qwen Code project worktrees excluded' { (StatusOf 'gem/.gemini/worktrees') -eq 'skipped_excluded' -and (StatusOf 'gem/.qwen/worktrees') -eq 'skipped_excluded' -and $null -eq (Row 'gem/.gemini/worktrees/w1/f') -and $null -eq (Row 'gem/.qwen/worktrees/w1/f') }
Check '#216 Gemini CLI project settings beside the worktrees collected' { ($r = Row 'gem/.gemini/settings.json') -and $r.agent -eq 'gemini-cli' -and $r.status -eq 'collected' }

# 2026-10-21 Hermes quick snapshots and desktop connections (#123, #208)
Check '#123 Hermes quick snapshot state.db collected' { (Is113 "$q123/state.db" 'hermes' $false) -and (Is113 "$q123/manifest.json" 'hermes' $false) -and (Is113 "$w123/state.db" 'hermes' $false) -and (StatusOf 'Users/alice/.hermes/state-snapshots') -eq '' }
Check '#123 Hermes quick snapshot credentials flagged secret' { (Is113 "$q123/.env" 'hermes' $true) -and (Is113 "$q123/auth.json" 'hermes' $true) -and (Is113 "$q123/pairing/telegram-approved.json" 'hermes' $true) }
Check '#208 Hermes desktop connection files flagged secret' { (Is113 'Users/alice/.config/Hermes/connections.json' 'hermes' $true) -and (Is113 'Users/alice/.config/Hermes/connection.json' 'hermes' $true) }

# 2026-10-21 nanobot workspace cron and triggers (#220)
function Is220([string]$rel) { $r = Row $rel; return ($r -and $r.agent -eq 'nanobot' -and $r.status -eq 'collected') }
Check '#220 nanobot workspace cron jobs and runs collected' { (Is220 'nanows/cron/jobs.json') -and (Is220 'nanows/cron/runs/j1_1_ab.json') }
Check '#220 nanobot workspace triggers and runs collected' { (Is220 'nanows/triggers/triggers.json') -and (Is220 'nanows/triggers/runs/d1.json') }
Check '#220 nanobot trigger queue not collected' { @($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like '*nanows/triggers/inbox*' }).Count -eq 0 }

# 2026-10-21 OpenClaw source review (#219)
Check '#219 OpenClaw exec-approvals.json flagged secret' { Is113 "$o219/exec-approvals.json" 'openclaw' $true }
Check '#219 OpenClaw auth-profile secrets directory flagged secret' { Is113 'Users/alice/.openclaw-auth-profile-secrets/gateway.env' 'openclaw' $true }
Check '#219 OpenClaw volume exec-approvals.json flagged secret' { $r = Row "$v219/exec-approvals.json"; $r -and $r.user -eq 'docker' -and $r.secret -eq $true -and $r.status -eq 'collected' }
Check '#219 OpenClaw Gateway clone excluded' { (StatusOf "$o219/projects/$c219") -eq 'skipped_excluded' -and (NoRow6 "$c219/repo/README.md") }
Check '#219 OpenClaw projects entry that is no clone collected' { Is113 "$o219/projects/notes/todo.md" 'openclaw' $false }
Check '#219 OpenClaw volume clone, plugin-skills and agent tmp excluded' { (StatusOf "$v219/projects/$c219") -eq 'skipped_excluded' -and (StatusOf "$v219/plugin-skills") -eq 'skipped_excluded' -and (StatusOf "$v219/agents/main/agent/tmp") -eq 'skipped_excluded' -and (StatusOf "$v219/agents/main/agent/.tmp") -eq 'skipped_excluded' }
Check '#219 volume projects entry that is no clone collected' { $r = Row "$v219/projects/p219/notes.md"; $r -and $r.user -eq 'docker' -and $r.status -eq 'collected' }

# 2026-10-21 OpenCode and Kilo Code source review (#213, #221)
Check '#213 OpenCode service.json flagged secret' { (Is113 'Users/alice/.config/opencode/service.json' 'opencode' $true) -and (Is113 'Users/alice/.local/state/opencode/service-local.json' 'opencode' $true) }
Check '#213 OpenCode desktop data collected' { (Is113 "$d213/drafts.sqlite" 'opencode' $false) -and (Is113 'Users/alice/.config/ai.opencode.desktop.beta/drafts.sqlite' 'opencode' $false) -and (Is113 'Users/alice/AppData/Roaming/ai.opencode.desktop/drafts.sqlite' 'opencode' $false) }
Check '#213 OpenCode desktop compile-cache excluded' { (StatusOf "$d213/compile-cache") -eq 'skipped_excluded' -and (NoRow6 'compile-cache/x') }
Check '#213 OpenCode Windows temp root collected' { Is113 'Users/alice/AppData/Local/Temp/opencode/notes.txt' 'opencode' $false }
Check '#221 Kilo sandbox policy and preference collected' { (Is113 "$k221/bb.json" 'kilo-code' $false) -and (Is113 'Users/alice/.local/state/kilo-sandbox-preference/bb.json' 'kilo-code' $false) }

# 2026-10-21 Qwen Code session registry (#230)
Check '#230 Qwen Code session registry flagged secret' { (Is113 'Users/alice/.qwen/sessions/4242.json' 'qwen-code' $true) -and (Is113 'Users/alice/.qwen/sessions/4243-0123abcd.json' 'qwen-code' $true) }

# 2026-10-21 Roo Code CLI cloud credentials (#159)
$r159 = Row 'Users/alice/.roo/cli-credentials.json'
Check '#159 roo cli-credentials.json flagged secret' { $r159 -and $r159.agent -eq 'roo-code' -and $r159.secret -eq $true -and $r159.status -eq 'collected' }

# 2026-10-21 Twinny workspace storage (#215)
Check '#215 twinny workspaceStorage agent-changes attributed to twinny' { $r = Row "$t215/rjmacarthy.twinny/agent-changes/c1.json"; $r -and $r.agent -eq 'twinny' -and $r.status -eq 'collected' }
Check '#215 twinny workspaceStorage neighbour stays vscode' { $r = Row "$t215/workspace.json"; $r -and $r.agent -eq 'vscode' -and $r.status -eq 'collected' }
Check '#215 twinny-server forge repos.json flagged secret' { $r = Row 'Users/alice/.twinny/server/plugins/github/repos.json'; $r -and $r.agent -eq 'twinny' -and $r.status -eq 'collected' -and $r.secret -eq $true }

# 2026-10-21 project git metadata (#253)
# Is253 FILE...: each file under the project's .git has a collected row with
# agent project and the project as its home. NoRow253 PREFIX...: no manifest
# row of the project names a path under its .git that starts with it. Both
# look only at rows whose home is the project, because Row matches a path
# suffix and proj/.git/HEAD also ends the Copilot Desktop clone at
# repos/proj/.git (#147), whose rows are copilot-desktop and whose objects/
# has a skipped_excluded row.
function Rows253 { return @($script:Rows | Where-Object { ($_.home -replace '\\', '/').EndsWith('/proj') }) }
function Is253([string[]]$files) {
  foreach ($f in $files) {
    $r = Rows253 | Where-Object { ($_.path -replace '\\', '/').EndsWith("/$g253/$f") } | Select-Object -First 1
    if (-not ($r -and $r.agent -eq 'project' -and $r.status -eq 'collected')) { return $false }
  }
  return $true
}
function NoRow253([string[]]$prefixes) {
  foreach ($p in $prefixes) {
    if (@(Rows253 | Where-Object { ($_.path -replace '\\', '/') -like "*/$g253/$p*" }).Count -ne 0) { return $false }
  }
  return $true
}
Check '#253 project git HEAD, config, FETCH_HEAD and packed-refs collected as project' { Is253 @('HEAD', 'config', 'FETCH_HEAD', 'packed-refs') }
Check '#253 project git refs and logs collected as project' { Is253 @('refs/heads/main', 'refs/remotes/origin/main', 'logs/HEAD', 'logs/refs/remotes/origin/main') }
Check '#253 project git worktrees collected as project' { Is253 @('worktrees/wt1/HEAD', 'worktrees/wt1/gitdir') }
Check '#253 project git linked worktree index excluded' { $r = Rows253 | Where-Object { ($_.path -replace '\\', '/').EndsWith("/$g253/worktrees/wt1/index") } | Select-Object -First 1; $r -and $r.status -eq 'skipped_excluded' }
Check '#253 project git linked worktree submodules excluded' { $r = Rows253 | Where-Object { ($_.path -replace '\\', '/').EndsWith("/$g253/worktrees/wt1/modules") } | Select-Object -First 1; $r -and $r.status -eq 'skipped_excluded' -and (NoRow253 @('worktrees/wt1/modules/sub')) }
Check '#253 project git linked worktree index.lock and sharedindex excluded' { $l = Rows253 | Where-Object { ($_.path -replace '\\', '/').EndsWith("/$g253/worktrees/wt1/index.lock") } | Select-Object -First 1; $s = Rows253 | Where-Object { ($_.path -replace '\\', '/').EndsWith("/$g253/worktrees/wt1/sharedindex.3333333333333333333333333333333333333333") } | Select-Object -First 1; $l -and $l.status -eq 'skipped_excluded' -and $s -and $s.status -eq 'skipped_excluded' }
Check '#253 project git objects, index, hooks, lfs and modules have no row' { NoRow253 @('objects', 'index', 'hooks', 'lfs', 'modules') }
Check '#253 project git config not flagged secret' { $r = Rows253 | Where-Object { ($_.path -replace '\\', '/').EndsWith("/$g253/config") } | Select-Object -First 1; $r -and $r.secret -eq $false -and $r.status -eq 'collected' }

# 2026-10-23 claude-code Windows round (#256)
Check '#256 Claude Code Windows temp root collected as claude-code' { (Is113 "$t256/scratchpad/notes.txt" 'claude-code' $false) -and (Is113 "$t256/tasks/b256b256b.output" 'claude-code' $false) }
Check '#256 home-level .claude.json.backup flagged secret' { Is113 'Users/alice/.claude.json.backup' 'claude-code' $true }
Check '#256 Claude Code daemon keys and roster flagged secret' { (Is113 'Users/alice/.claude/daemon/control.key' 'claude-code' $true) -and (Is113 'Users/alice/.claude/daemon/pipe.key' 'claude-code' $true) -and (Is113 'Users/alice/.claude/daemon/roster.json' 'claude-code' $true) }
Check '#256 Claude Code .claude.json backup flagged secret' { Is113 'Users/alice/.claude/backups/.claude.json.backup.1792800000000' 'claude-code' $true }
Check '#256 Claude Code corrupted .claude.json copy flagged secret' { Is113 'Users/alice/.claude/backups/.claude.json.corrupted.2026-10-23T17-00-00-000Z' 'claude-code' $true }
Check '#256 Claude Code paste-cache collected' { Is113 'Users/alice/.claude/paste-cache/0123456789abcdef.txt' 'claude-code' $false }
Check '#256 Claude Code plugin directory cache excluded' { (StatusOf 'Users/alice/.claude/plugins/plugin-directory-cache-v2.json') -eq 'skipped_excluded' }
Check '#256 project git info/exclude collected as project' { Is253 @('info/exclude') }

# 2026-10-26 claude-code Linux round (#256)
Check '#256 Claude Code version lock collected as claude-code' { Is113 'Users/alice/.local/state/claude/locks/2.1.310.lock' 'claude-code' $false }
Check '#256 Claude Code cache staging collected as claude-code' { Is113 'Users/alice/.cache/claude/staging/entry' 'claude-code' $false }

# 2026-10-26 claude-code macOS round (#256)
Check '#256 Claude Code URL handler bundle collected as claude-code' { $r = Row "$u256/MacOS/claude"; (Is113 "$u256/Info.plist" 'claude-code' $false) -and ((-not $link256) -or ($r -and $r.agent -eq 'claude-code' -and $r.type -eq 'symlink' -and $r.status -eq 'symlink' -and ($r.target -replace '\\', '/') -like '*.local/bin/claude')) }
Check '#256 Claude Code IDE lock and bridge-spawn mcp.json flagged secret' { (Is113 'Users/alice/.claude/ide/53256.lock' 'claude-code' $true) -and (Is113 "Users/alice/.claude/$s256/mcp.json" 'claude-code' $true) -and (Is113 "Users/alice/.claude/$s256/append-system-prompt.txt" 'claude-code' $false) }
Check '#256 relocated claude home IDE lock and bridge-spawn mcp.json flagged secret' { (Is113 'Users/alice/.claude-work/ide/53256.lock' 'claude-code' $true) -and (Is113 "Users/alice/.claude-work/$s256/mcp.json" 'claude-code' $true) }

# cross-check archived bytes against manifest hashes
$x = Join-Path $Work 'x'; New-Item -ItemType Directory -Path $x -Force | Out-Null
if ($script:A.Name -like '*.tar.gz') { & tar -xzf $script:A.FullName -C $x 2>$null } else { [System.IO.Compression.ZipFile]::ExtractToDirectory($script:A.FullName, $x) }
$n = Test-ArchivedHashes $x
Check "archived file bytes match manifest hashes ($n files)" { $n -gt 10 }
# 2026-10-14 manifest size of a collected file (#111): the size is the byte
# count the copy wrote, so it equals the archive member's length. CI cannot
# make NTFS report a stale length, so this guards the plumbing only.
$r111 = Row "$g83/conversations/a1.db"
$f111 = $null; if ($r111) { $f111 = XP (Join-Path $x ($r111.archive_path.Replace('/', $Sep))) }
Check '#111 collected size is the length of the archived copy' { $r111 -and $r111.size -eq 6 -and (Get-Item -LiteralPath $f111 -Force).Length -eq $r111.size }
# 2026-10-10 long paths (#77): the deep transcript, by its plain path.
$r77 = Row $Deep77
Check '#77 deep transcript collected as claude-code under its plain path' { $r77 -and $r77.status -eq 'collected' -and $r77.agent -eq 'claude-code' -and $r77.path -eq (P $Deep77) -and -not $r77.path.StartsWith('\\?\') -and $r77.error -eq '' }
Check '#77 deep transcript sha256 matches its content and the archived bytes' { $r77 -and $r77.sha256 -eq $Sha77 -and (Get-FileHash -LiteralPath (XP (Join-Path $x ($r77.archive_path.Replace('/', $Sep)))) -Algorithm SHA256).Hash.ToLower() -eq $Sha77 }
Check '#77 archive lists the deep transcript' { $r77 -and $r77.archive_path -eq ('fs/' + $Deep77) -and @($DefaultEntries | Where-Object { $_ -eq ('./' + $r77.archive_path) -or $_ -eq $r77.archive_path }).Count -eq 1 }

# 2026-10-07 (#71): every line parses when read as UTF-8, and each name that
# needs escaping comes back unchanged in path. The hash cross-check above
# covers these files too: their archived bytes match the manifest sha256.
function Read-Manifest71([string]$file) {
  $raw = @([System.IO.File]::ReadAllLines($file, (New-Object System.Text.UTF8Encoding $false)))
  $rows = @(); $errs = 0
  foreach ($l in $raw) { try { $rows += ($l | ConvertFrom-Json) } catch { $errs++ } }
  return @{ count = $raw.Count; rows = $rows; errors = $errs }
}
$m71 = Read-Manifest71 $script:M.FullName
Check '#71 every manifest line parses as JSON' { $m71.errors -eq 0 -and $m71.rows.Count -eq $m71.count -and $m71.count -gt 10 }
foreach ($n71 in $Names71) {
  $w71 = [System.IO.Path]::Combine($Dir71, $n71)
  Check "#71 path round-trips through the manifest: $($n71 -replace '[^\x20-\x7e]', '?')" { @($m71.rows | Where-Object { $_.path -ceq $w71 -and $_.status -eq 'collected' -and $_.archive_path }).Count -eq 1 }
}
# Non-ASCII names, and on Windows a lone surrogate, which the UTF-8 writer
# turns into U+FFFD as ConvertTo-Json's output did. They are collected from an
# image of their own, whose archive Windows tar.exe cannot write (#72 below
# checks the fallback). The sha256 is checked against the source, whose bytes
# are known.
$Root71 = Join-Path $Work 'root71'
$UDir71 = [System.IO.Path]::Combine($Root71, 'Users', 'alice', '.claude', 'projects', '-C-u71')
[void][System.IO.Directory]::CreateDirectory($UDir71)
$UNames71 = @(('u' + [char]0x00FC + 'ml' + [char]0x00E9 + '.jsonl'), ([string][char]0x65E5 + [char]0x672C + ' ' + [char]0x8A9E + '.jsonl'), ([string][char]0x0416 + [char]0x0443 + [char]0x0440 + [char]0x043D + [char]0x0430 + [char]0x043B + '.jsonl'))
foreach ($n71 in $UNames71) { [System.IO.File]::WriteAllText([System.IO.Path]::Combine($UDir71, $n71), '{"type":"user"}', (New-Object System.Text.UTF8Encoding $false)) }
# 2026-10-07 (#72): a symlink with a Cyrillic name and an absolute target
# with a CJK name, which goes in a pax linkpath record.
$Link72 = [string][char]0x0441 + [char]0x0441 + [char]0x044B + [char]0x043B + [char]0x043A + [char]0x0430 + '.jsonl'
$Link72Target = [System.IO.Path]::Combine($UDir71, $UNames71[1])
try { New-Item -ItemType SymbolicLink -Path ([System.IO.Path]::Combine($UDir71, $Link72)) -Target $Link72Target -ErrorAction Stop | Out-Null }
catch { $Link72 = ''; Write-Output 'note: symlink creation not permitted here, #72 non-ASCII symlink check skipped' }
$Lone71 = ''
if ($Sep -ne '/') {
  $Lone71 = 'lone' + [char]0xD800 + '.jsonl'
  try { [System.IO.File]::WriteAllText([System.IO.Path]::Combine($UDir71, $Lone71), '{"type":"user"}', (New-Object System.Text.UTF8Encoding $false)) }
  catch { $Lone71 = ''; Write-Output 'note: #71 lone-surrogate name not allowed here, check skipped' }
}
$o71 = Join-Path $Out 'u71'
New-Item -ItemType Directory -Path $o71 -Force | Out-Null
$c71 = @{ Root = $Root71; OutputDir = $o71; Quiet = $true; NoDocker = $true }
$global:LASTEXITCODE = 0
& $Collector @c71 *> $null
$rc71 = $LASTEXITCODE
$um71 = Read-Manifest71 (Get-ChildItem -LiteralPath $o71 -Filter '*.manifest.jsonl' | Select-Object -First 1).FullName
$sha71 = (Get-FileHash -LiteralPath ([System.IO.Path]::Combine($UDir71, $UNames71[0])) -Algorithm SHA256).Hash.ToLower()
Check '#71 non-ASCII image: exit 0 and every manifest line parses' { $rc71 -eq 0 -and $um71.errors -eq 0 -and $um71.rows.Count -eq $um71.count -and $um71.count -ge $UNames71.Count }
foreach ($n71 in $UNames71) {
  $w71 = [System.IO.Path]::Combine($UDir71, $n71)
  Check "#71 non-ASCII path round-trips with its sha256: $($n71 -replace '[^\x20-\x7e]', '?')" { @($um71.rows | Where-Object { $_.path -ceq $w71 -and $_.status -eq 'collected' -and $_.sha256 -eq $sha71 }).Count -eq 1 }
}
if ($Lone71) {
  $w71 = [System.IO.Path]::Combine($UDir71, $Lone71.Replace([string][char]0xD800, [string][char]0xFFFD))
  Check '#71 lone surrogate in a name is written as U+FFFD' { @($um71.rows | Where-Object { $_.path -ceq $w71 -and $_.status -eq 'collected' -and $_.sha256 -eq $sha71 }).Count -eq 1 }
}

# 2026-10-07 (#72): some Windows tar.exe builds exit 0xC0000005 on a name
# outside the ANSI code page. The collector logs the exit code, notes the fallback, and
# writes the .tar.gz with its own tar writer, which keeps every name and the
# staged links. Elsewhere the system tar writes it. Read with .NET, since
# tar.exe cannot list these names either.
$a71 = Get-ChildItem -LiteralPath $o71 | Where-Object { $_.Name -match '\.(tar\.gz|zip)$' } | Select-Object -First 1
$s71 = Get-Content -LiteralPath (Get-ChildItem -LiteralPath $o71 -Filter '*.collection.json' | Select-Object -First 1).FullName -Raw | ConvertFrom-Json
$l71 = [System.IO.File]::ReadAllText((Get-ChildItem -LiteralPath $o71 -Filter '*.log' | Select-Object -First 1).FullName)
Check '#72 non-ASCII image archived as a .tar.gz named in collection.json' { $a71 -and $a71.Name -like '*.tar.gz' -and $s71.archive -eq $a71.Name }
# Not every tar.exe build crashes (the windows-latest runner's stores these
# names), so the fallback checks follow the archiver that ran; the forced tar
# failure further down tests the fallback on every host.
if ($env:OS -eq 'Windows_NT' -and (Get-Command tar.exe -ErrorAction SilentlyContinue)) {
  if ($s71.capabilities.archiver -eq 'tar.exe') {
    Write-Output 'note: tar.exe stored the non-ASCII names here; #72 fallback checked through the forced tar failure only'
    Check '#72 Windows: tar.exe wrote it, so no fallback note' { @($s71.notes | Where-Object { $_ -match '^tar\.exe failed' }).Count -eq 0 }
  } else {
    Check '#72 Windows: the PowerShell tar writer wrote it after tar.exe failed' { $s71.capabilities.archiver -eq 'PowerShell tar writer' }
    Check '#72 Windows: notes give the tar.exe exit code and the fallback' { @($s71.notes | Where-Object { $_ -match '^tar\.exe failed \(exit code 0x[0-9A-F]{8}\); fell back to PowerShell tar writer$' }).Count -eq 1 }
    Check '#72 Windows: the log gives the tar.exe exit code' { $l71 -match '(?m)^tar\.exe failed: exit code 0x[0-9A-F]{8}\r?$' }
  }
}
# Checked for the default run and for one with the writer forced, so the pax
# records are tested on every platform; the forced one is also extracted with
# the platform tar where its tar can store these names (not Windows tar.exe).
$o72 = Join-Path $Out 'u72w'
New-Item -ItemType Directory -Path $o72 -Force | Out-Null
$env:CAC_ARCHIVER = 'writer'
$global:LASTEXITCODE = 0
try { & $Collector -Root $Root71 -OutputDir $o72 -Quiet -NoDocker *> $null } finally { Remove-Item Env:CAC_ARCHIVER }
$rc72 = $LASTEXITCODE
$a72 = Get-ChildItem -LiteralPath $o72 | Where-Object { $_.Name -match '\.tar\.gz$' } | Select-Object -First 1
$um72 = Read-Manifest71 (Get-ChildItem -LiteralPath $o72 -Filter '*.manifest.jsonl' | Select-Object -First 1).FullName
Check '#72 non-ASCII image, writer forced: exit 0 and a .tar.gz' { $rc72 -eq 0 -and $a72 }
$want71 = @($UNames71); if ($Lone71) { $want71 += $Lone71.Replace([string][char]0xD800, [string][char]0xFFFD) }
# tar.exe rewrites a link target (\\?\ prefix, / separators, and on a runner
# a resolved short path; docs/windows.md), so for its archive only the target's
# file name is compared, and the stored target is printed for diagnosis.
foreach ($pair in @(@('', $a71, $um71, [string]$s71.capabilities.archiver), @(' [writer]', $a72, $um72, 'PowerShell tar writer'))) {
  $tag = $pair[0]; $t71 = Read-TarGz $pair[1].FullName; $rows72 = $pair[2].rows
  Check ('#72 non-ASCII archive: header checksums valid, two zero blocks at the end' + $tag) { $t71.badsum -eq 0 -and $t71.end -and $t71.members.Count -gt 3 }
  foreach ($n71 in $want71) {
    $row71 = @($rows72 | Where-Object { $_.path -ceq ([System.IO.Path]::Combine($UDir71, $n71)) }) | Select-Object -First 1
    Check ("#72 non-ASCII name round-trips through the archive with its sha256: $($n71 -replace '[^\x20-\x7e]', '?')" + $tag) { $row71 -and @($t71.members | Where-Object { $_.name -ceq ('./' + $row71.archive_path) -and $_.type -eq '0' -and $_.sha256 -eq $row71.sha256 -and $_.sha256 -eq $sha71 }).Count -eq 1 }
  }
  if ($Link72) {
    $row72 = @($rows72 | Where-Object { $_.path -ceq ([System.IO.Path]::Combine($UDir71, $Link72)) }) | Select-Object -First 1
    if ($pair[3] -eq 'tar.exe' -and $row72) { $lk72 = @($t71.members | Where-Object { $_.name -ceq ('./' + $row72.archive_path) }) | Select-Object -First 1; if ($lk72) { Write-Output ('note: tar.exe stored the #72 link target as ' + ([string]$lk72.link -replace '[^\x20-\x7e]', '?')) } }
    Check ('#72 non-ASCII symlink kept in the archive with its target' + $tag) { $row72 -and $row72.status -eq 'symlink' -and $row72.archive_path -and @($t71.members | Where-Object { $_.name -ceq ('./' + $row72.archive_path) -and $_.type -eq '2' -and ($_.link -ceq $Link72Target -or ($pair[3] -eq 'tar.exe' -and $_.link.Replace('\', '/').EndsWith('/' + $UNames71[1], [System.StringComparison]::Ordinal))) }).Count -eq 1 }
  }
}
if ($Sep -eq '/') {
  $x72u = Join-Path $Work 'x72u'; New-Item -ItemType Directory -Path $x72u -Force | Out-Null
  & tar -xzf $a72.FullName -C $x72u 2>$null
  $rcx = $LASTEXITCODE
  $rx = @($um72.rows | Where-Object { $_.status -eq 'collected' -and $_.archive_path })
  Check '#72 non-ASCII archive from the writer extracts with the platform tar' { $rcx -eq 0 -and $rx.Count -ge $want71.Count -and @($rx | Where-Object { -not (Test-Path -LiteralPath ([System.IO.Path]::Combine($x72u, $_.archive_path))) }).Count -eq 0 }
}

# The writer forced with CAC_ARCHIVER on the main image, on every platform:
# the platform tar lists and extracts it, the members are the default run's,
# and the archived bytes match the manifest.
$env:CAC_ARCHIVER = 'writer'
try { Run 'writer72' @{} } finally { Remove-Item Env:CAC_ARCHIVER }
$w72 = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json
Check '#72 forced writer: exit 0, .tar.gz, archiver PowerShell tar writer' { $script:rc -eq 0 -and $script:A.Name -like '*.tar.gz' -and $w72.archive -eq $script:A.Name -and $w72.capabilities.archiver -eq 'PowerShell tar writer' -and @($w72.notes).Count -eq @($dsum0.notes).Count }
$WriterEntries = @(ArchiveEntries)
Check '#72 forced writer: platform tar lists the same members as the default run' { $WriterEntries.Count -gt 10 -and ((Join-Sorted $WriterEntries) -ceq (Join-Sorted $DefaultEntries)) }
$x72 = Join-Path $Work 'x72'; New-Item -ItemType Directory -Path $x72 -Force | Out-Null
& tar -xzf $script:A.FullName -C $x72 2>$null
$rcx72 = $LASTEXITCODE
$n72 = Test-ArchivedHashes $x72
Check "#72 forced writer: platform tar extracts it and the bytes match the manifest ($n72 files)" { $rcx72 -eq 0 -and $n72 -gt 10 }
$tw72 = Read-TarGz $script:A.FullName
Check '#72 forced writer: header checksums valid, two zero blocks at the end' { $tw72.badsum -eq 0 -and $tw72.end }
if ($linkOk) { Check '#72 forced writer: the main image symlink is stored as a link' { @($tw72.members | Where-Object { $_.type -eq '2' -and $_.name -like '*antigravity-cli/cli.log' }).Count -eq 1 } }
Check '#77 built-in tar writer stores the deep transcript' { $r77w = Row $Deep77; $r77w -and @($tw72.members | Where-Object { $_.type -eq '0' -and $_.name -eq ('./' + $r77w.archive_path) -and $_.sha256 -eq $Sha77 }).Count -eq 1 -and (Get-FileHash -LiteralPath (XP (Join-Path $x72 ($r77w.archive_path.Replace('/', $Sep)))) -Algorithm SHA256).Hash.ToLower() -eq $Sha77 }

# The zip forced with CAC_ARCHIVER: entry names use /, are the writer's file
# members without ./, and hold the manifest's bytes.
$env:CAC_ARCHIVER = 'zip'
try { Run 'zip72' @{} } finally { Remove-Item Env:CAC_ARCHIVER }
$z72 = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json
Check '#72 forced zip: exit 0, .zip, archiver ZipFile' { $script:rc -eq 0 -and $script:A.Name -like '*.zip' -and $z72.archive -eq $script:A.Name -and $z72.capabilities.archiver -eq 'ZipFile' }
$ZipEntries = @(ArchiveEntries)
$wantZip = @($tw72.members | Where-Object { $_.type -eq '0' } | ForEach-Object { $_.name.Substring(2) })
$gotZip = @($ZipEntries | Where-Object { -not $_.EndsWith('/') })
Check '#72 forced zip: entry names use / and match the tar members' { @($ZipEntries | Where-Object { $_ -like 'fs/*/*' }).Count -gt 10 -and ((Join-Sorted $gotZip) -ceq (Join-Sorted $wantZip)) }
if ($Sep -eq '\') { Check '#72 forced zip: no entry name has a backslash' { @($ZipEntries | Where-Object { $_.Contains('\') }).Count -eq 0 } }
Check '#72 forced zip: archived bytes match the manifest' {
  $z = [System.IO.Compression.ZipFile]::OpenRead($script:A.FullName)
  $nz = 0; $badz = 0
  try {
    foreach ($row in ($script:Rows | Where-Object { $_.status -eq 'collected' -and $_.archive_path })) {
      $e = $z.GetEntry($row.archive_path)
      if ($null -eq $e) { $badz++; continue }
      $st = $e.Open()
      try { $hz = ([BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($st)) -replace '-', '').ToLower() } finally { $st.Dispose() }
      if ($hz -ne $row.sha256) { $badz++ }
      $nz++
    }
  } finally { $z.Dispose() }
  $badz -eq 0 -and $nz -gt 10
}
Check '#77 forced zip stores the deep transcript' { $r77z = Row $Deep77; $r77z -and $r77z.status -eq 'collected' -and @($ZipEntries | Where-Object { $_ -eq $r77z.archive_path }).Count -eq 1 }

# ---- -NoSecrets -----------------------------------------------------------
Run 'nosecrets' @{ NoSecrets = $true }
Check 'NoSecrets exit 0' { $script:rc -eq 0 }
Check 'credentials skipped_secret' { (StatusOf 'Users/alice/.claude/.credentials.json') -eq 'skipped_secret' }
Check 'credentials absent from archive' { -not (ArchiveEntries | Where-Object { $_ -match 'credentials\.json$' }) }
# 2026-10-11 Claude Desktop Linux deb and Claude Code 2.1.295 session keys (#73, #76)
Check '#73 #76 NoSecrets skips link-key and the session key' { (StatusOf $l76) -eq 'skipped_secret' -and (StatusOf $k76) -eq 'skipped_secret' }
# 2026-10-13 Antigravity desktop app (#83, #84)
Check '#84 Antigravity plugin token skipped without secrets' { (StatusOf "$g83/plugin_data/gdocs/token.json") -eq 'skipped_secret' }
# 2026-10-13 Antigravity Linux round (#83, #90, #91)
Check '#90 Antigravity CLI plugin-secrets.json skipped without secrets' { (StatusOf "$w83/plugin-secrets.json") -eq 'skipped_secret' }
# 2026-10-15 ChatGPT desktop as the OpenAI.Codex package (#113)
Check '#115 Codex desktop global state skipped without secrets' { (StatusOf 'Users/alice/.codex/.codex-global-state.json') -eq 'skipped_secret' }
# 2026-10-16 GitHub Copilot Desktop (#147)
Check '#147 Copilot Desktop ws.token skipped without secrets' { (StatusOf "$d147/run/ws.token") -eq 'skipped_secret' }
# 2026-10-17 session sync round (#153)
Check '#153 nanobot remote pairing keys skipped without secrets' { (StatusOf "$n153/identity") -eq 'skipped_secret' -and (StatusOf "$n153/exchange") -eq 'skipped_secret' }
Check '#153 Agent Zero plugin config.json skipped without secrets' { (StatusOf "Users/alice/agent-zero/main/usr/$t153") -eq 'skipped_secret' -and (StatusOf "Users/alice/Desktop/agent-zero/usr/$t153") -eq 'skipped_secret' }
Check '#153 Agent Zero volume plugin config.json skipped without secrets' { (StatusOf "$v153/$t153") -eq 'skipped_secret' -and (StatusOf "$v153/usr/$t153") -eq 'skipped_secret' }
Check '#153 Cline cached remote config skipped without secrets' { (StatusOf "$g153/remote_config_org1.json") -eq 'skipped_secret' }
Check '#153 Cline webhook_config.json skipped without secrets' { (StatusOf 'Users/alice/Documents/Cline/webhook_config.json') -eq 'skipped_secret' }
Check '#153 Gemini CLI bug-memory heap snapshot skipped without secrets' { (StatusOf 'Users/alice/.gemini/tmp/gem/bug-memory-1792000000000.heapsnapshot') -eq 'skipped_secret' }
Check '#153 little-coder legacy config.json skipped without secrets' { (StatusOf 'Users/alice/.little-coder/config.json') -eq 'skipped_secret' }
Check '#153 Qwen Code channel credentials skipped without secrets' { (StatusOf 'Users/alice/.qwen/channels/qqbot-credentials.json') -eq 'skipped_secret' -and (StatusOf 'Users/alice/.qwen/channels/weixin/account.json') -eq 'skipped_secret' }
Check '#153 Qwen Code channel routing files kept without secrets' { (StatusOf 'Users/alice/.qwen/channels/sessions.json') -eq 'collected' -and (StatusOf 'Users/alice/.qwen/channels/daemon/0123abcd/routes.json') -eq 'collected' }
# 2026-10-18 Codex shell snapshots (#160)
Check '#160 Codex shell snapshot skipped without secrets' { (StatusOf $s160) -eq 'skipped_secret' }
# 2026-10-21 framework catalog gaps (#223, #224, #225)
Check '#224 difyctl login-pending.yml skipped without secrets' { (StatusOf 'Users/alice/.config/difyctl/login-pending.yml') -eq 'skipped_secret' }
Check '#225 CLAI 2.0 workspace token skipped without secrets' { (StatusOf "$p225/workspaces/registry/ws1/token") -eq 'skipped_secret' }

# 2026-10-21 Agent Zero source review (#217)
Check '#217 Agent Zero WhatsApp session skipped without secrets' { (StatusOf "Users/alice/agent-zero/main/$w217") -eq 'skipped_secret' -and (StatusOf "Users/alice/Desktop/agent-zero/$w217") -eq 'skipped_secret' -and (StatusOf "var/lib/docker/volumes/a0_usr/_data/$w217") -eq 'skipped_secret' }

# 2026-10-21 Cody JetBrains plugin files (#214)
Check '#214 Cody cody_accounts.xml skipped without secrets' { (StatusOf "$o214/cody_accounts.xml") -eq 'skipped_secret' }
Check '#214 Cody cody.xml skipped without secrets' { (StatusOf "$o214/cody.xml") -eq 'skipped_secret' }
Check '#214 Cody cody_settings.json skipped without secrets' { ((StatusOf 'Users/alice/.sourcegraph/cody_settings.json') -eq 'skipped_secret') -and ((StatusOf 'proj/.idea/.sourcegraph/cody_settings.json') -eq 'skipped_secret') }

# 2026-10-21 Hermes quick snapshots and desktop connections (#123, #208)
Check '#123 Hermes quick snapshot credentials skipped without secrets' { (StatusOf "$q123/.env") -eq 'skipped_secret' -and (StatusOf "$q123/auth.json") -eq 'skipped_secret' -and (StatusOf "$q123/state.db") -eq 'collected' }
Check '#208 Hermes desktop connection files skipped without secrets' { (StatusOf 'Users/alice/.config/Hermes/connections.json') -eq 'skipped_secret' }

# 2026-10-21 OpenClaw source review (#219)
Check '#219 OpenClaw credentials skipped without secrets' { (StatusOf "$o219/exec-approvals.json") -eq 'skipped_secret' -and (StatusOf 'Users/alice/.openclaw-auth-profile-secrets/gateway.env') -eq 'skipped_secret' -and (StatusOf "$v219/exec-approvals.json") -eq 'skipped_secret' }

# 2026-10-21 OpenCode and Kilo Code source review (#213, #221)
Check '#213 OpenCode service.json skipped without secrets' { (StatusOf 'Users/alice/.config/opencode/service.json') -eq 'skipped_secret' -and (StatusOf 'Users/alice/.local/state/opencode/service-local.json') -eq 'skipped_secret' }

# 2026-10-21 Qwen Code session registry (#230)
Check '#230 Qwen Code session registry skipped without secrets' { (StatusOf 'Users/alice/.qwen/sessions/4242.json') -eq 'skipped_secret' -and (StatusOf 'Users/alice/.qwen/sessions/4243-0123abcd.json') -eq 'skipped_secret' }

# 2026-10-23 claude-code Windows round (#256)
Check '#256 Claude Code daemon keys and .claude.json backup skipped without secrets' { (StatusOf 'Users/alice/.claude/daemon/control.key') -eq 'skipped_secret' -and (StatusOf 'Users/alice/.claude/daemon/roster.json') -eq 'skipped_secret' -and (StatusOf 'Users/alice/.claude/backups/.claude.json.backup.1792800000000') -eq 'skipped_secret' }
Check '#256 relocated claude home session key, daemon key and backup skipped without secrets' { (StatusOf $CcwK) -eq 'skipped_secret' -and (StatusOf 'Users/alice/.claude-work/daemon/control.key') -eq 'skipped_secret' -and (StatusOf 'Users/alice/.claude-work/backups/.claude.json.backup.1792800000000') -eq 'skipped_secret' }

# 2026-10-26 claude-code macOS round (#256)
Check '#256 Claude Code IDE lock and bridge-spawn mcp.json skipped without secrets' { (StatusOf 'Users/alice/.claude/ide/53256.lock') -eq 'skipped_secret' -and (StatusOf "Users/alice/.claude/$s256/mcp.json") -eq 'skipped_secret' -and (StatusOf 'Users/alice/.claude-work/ide/53256.lock') -eq 'skipped_secret' -and (StatusOf "Users/alice/.claude-work/$s256/mcp.json") -eq 'skipped_secret' }

# ---- -Full ----------------------------------------------------------------
Run 'full' @{ Full = $true }
Check 'Full exit 0' { $script:rc -eq 0 }
Check 'cache contents collected with -Full' { (StatusOf 'cache/junk.bin') -eq 'collected' }
# 2026-10-14 catalog match that is an excluded file (#107)
Check '#107 excluded file match collected with --full' { (StatusOf 'Users/alice/.local/bin/.muse-update.107.exe') -eq 'collected' }

# ---- -Users ---------------------------------------------------------------
Run 'users' @{ Users = 'bob' }
Check 'Users exit 0' { $script:rc -eq 0 }
Check 'only bob collected' { (-not ($script:Rows | Where-Object { $_.user -eq 'alice' })) -and ($script:Rows | Where-Object { $_.user -eq 'bob' }) }

# ---- -NoDocker -------------------------------------------------------------
Run 'nodocker' @{ NoDocker = $true }
Check 'NoDocker exit 0' { $script:rc -eq 0 }
Check 'NoDocker collects no volume' { -not ($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like '*docker/volumes*' }) }
$sum = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json
Check 'NoDocker recorded in options' { $sum.options.no_docker -eq $true }
Check 'NoDocker prints no docker line' { $script:stdout -notmatch '(?m)^docker:' }

# 2026-10-14 home patterns and the working directory (#105)
Push-Location -LiteralPath $cwd105
try { Run 'cwd105' @{ NoDocker = $true; NoProjects = $true } } finally { Pop-Location }
$users105 = ''
if ($script:S) { $users105 = @((Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json).users) -join ',' }
Check '#105 image homes found from a directory with home and Users subdirectories' { $script:rc -eq 0 -and ($script:Rows | Where-Object { $_.user -eq 'bob' }) -and $users105 -ne '' -and $users105 -eq (@($dsum0.users) -join ',') }

# 2026-10-14 NESTED_CLAIMS from the environment (#106)
# An inherited value naming a subtree of a matched volume must prune nothing,
# as in smoke.sh, where the sh collector once read it from the environment.
$env:NESTED_CLAIMS = P 'var/lib/docker/volumes/a0_usr/_data/chats'
try { Run 'claims106' @{ NoProjects = $true } } finally { Remove-Item Env:NESTED_CLAIMS }
Check '#106 NESTED_CLAIMS in the environment prunes nothing' { $script:rc -eq 0 -and (StatusOf 'var/lib/docker/volumes/a0_usr/_data/chats/ctx1/chat.json') -eq 'collected' }

# ---- Docker Desktop note ----------------------------------------------------
Mk 'Users/alice/AppData/Local/Docker/wsl/disk/readme.txt' 'vhdx lives here'
Run 'desktop' @{}
Check 'Docker Desktop exit 0' { $script:rc -eq 0 }
$sum = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json
Check 'Docker Desktop noted in collection.json' { $sum.docker.docker_desktop -eq $true -and @($sum.notes | Where-Object { $_ -like 'docker: Docker Desktop data at *' }).Count -eq 1 }
Check 'Docker Desktop noted in stdout' { $script:stdout -match '(?m)^docker:     3 volumes found, 2 collected, 0 unreadable; Docker Desktop VM disk not collected\s*$' }
Remove-Item -LiteralPath (P 'Users/alice/AppData/Local/Docker') -Recurse -Force

# 2026-10-06 frameworks sweep (#64): Dify, Langflow and n8n named volumes, in
# a run of their own so the volume counts above stay as they are. The n8n
# volume holds ~/.n8n, so its config (encryptionKey) is flagged through the
# volume-relative config glob.
$fv = 'var/lib/docker/volumes/n8n_data/_data'
Mk "$fv/config" '{"encryptionKey":"k"}'
Mk "$fv/database.sqlite" 'db'
Mk "$fv/nodes/node_modules/pkg/index.js" 'x'
Mk "$fv/node-definitions/d.json" 'x'
Mk "$fv/n8n-sdk-templates/t.json" 'x'
Mk "$fv/ssh/key" 'key'
Mk 'var/lib/docker/volumes/n8n_n8n-data/_data/database.sqlite' 'db'
Mk 'var/lib/docker/volumes/langflow_langflow-data/_data/secret_key' 'k'
Mk 'var/lib/docker/volumes/langflow_langflow-data/_data/cache_secret_key' 'k'
Mk 'var/lib/docker/volumes/langflow_langflow-data/_data/profile_pictures/p.svg' 'x'
Mk 'var/lib/docker/volumes/docker_dify_agent_local_sandbox_home/_data/.local/share/shellctl/shellctl.db' 'db'
Mk 'var/lib/docker/volumes/docker_dify_agent_local_sandbox_workspace/_data/out.txt' 'x'
# 2026-10-21 Hermes quick snapshots and desktop connections (#123, #208): a
# Hermes home in a named volume keeps its quick snapshots at the volume root,
# so their credential copies need the volume-relative secret globs.
$v123 = 'var/lib/docker/volumes/hermes_home/_data/state-snapshots/20261001-120004'
Mk "$v123/state.db" 'sqlite'
Mk "$v123/.env" 'KEY=x'
Mk "$v123/auth.json" '{"providers":{}}'
Mk "$v123/pairing/telegram-approved.json" '{}'
Run 'fwvolumes' @{}
Check 'frameworks volumes exit 0' { $script:rc -eq 0 }
$r = Row "$fv/database.sqlite"
Check 'n8n_data volume collected as n8n' { $r -and $r.user -eq 'docker' -and $r.agent -eq 'n8n' -and $r.status -eq 'collected' -and ($r.home -replace '\\', '/').EndsWith($fv) }
$r = Row "$fv/config"
Check 'n8n volume config flagged secret (volume-relative)' { $r -and $r.secret -eq $true -and $r.status -eq 'collected' }
$r = Row "$fv/ssh/key"
Check 'n8n volume ssh key flagged secret (volume-relative)' { $r -and $r.secret -eq $true -and $r.status -eq 'collected' }
Check 'n8n volume nodes/node_modules excluded (volume-relative)' { (StatusOf "$fv/nodes/node_modules") -eq 'skipped_excluded' }
Check 'n8n volume node-definitions excluded (volume-relative)' { (StatusOf "$fv/node-definitions") -eq 'skipped_excluded' }
Check 'n8n volume n8n-sdk-templates excluded (volume-relative)' { (StatusOf "$fv/n8n-sdk-templates") -eq 'skipped_excluded' }
$r = Row 'var/lib/docker/volumes/n8n_n8n-data/_data/database.sqlite'
Check 'n8n_n8n-data volume collected as n8n' { $r -and $r.agent -eq 'n8n' -and $r.status -eq 'collected' }
$r = Row 'var/lib/docker/volumes/langflow_langflow-data/_data/secret_key'
Check 'langflow-data volume secret_key flagged (volume-relative)' { $r -and $r.agent -eq 'langflow' -and $r.secret -eq $true -and $r.status -eq 'collected' }
$r = Row 'var/lib/docker/volumes/langflow_langflow-data/_data/cache_secret_key'
Check 'langflow-data volume cache_secret_key flagged (volume-relative)' { $r -and $r.secret -eq $true -and $r.status -eq 'collected' }
Check 'langflow-data volume profile_pictures excluded (volume-relative)' { (StatusOf 'var/lib/docker/volumes/langflow_langflow-data/_data/profile_pictures') -eq 'skipped_excluded' }
$r = Row 'var/lib/docker/volumes/docker_dify_agent_local_sandbox_home/_data/.local/share/shellctl/shellctl.db'
Check 'dify sandbox home volume collected as dify' { $r -and $r.agent -eq 'dify' -and $r.status -eq 'collected' }
$r = Row 'var/lib/docker/volumes/docker_dify_agent_local_sandbox_workspace/_data/out.txt'
Check 'dify sandbox workspace volume collected as dify' { $r -and $r.agent -eq 'dify' -and $r.status -eq 'collected' }
# 2026-10-21 Hermes quick snapshots and desktop connections (#123, #208)
$r = Row "$v123/state.db"
Check '#123 Hermes volume quick snapshot collected, credentials flagged (volume-relative)' { $r -and $r.user -eq 'docker' -and $r.agent -eq 'hermes' -and $r.secret -eq $false -and $r.status -eq 'collected' -and (Row "$v123/.env").secret -eq $true -and (Row "$v123/auth.json").secret -eq $true -and (Row "$v123/pairing/telegram-approved.json").secret -eq $true }
foreach ($v in @('n8n_data', 'n8n_n8n-data', 'langflow_langflow-data', 'docker_dify_agent_local_sandbox_home', 'docker_dify_agent_local_sandbox_workspace', 'hermes_home')) {
  Remove-Item -LiteralPath (P "var/lib/docker/volumes/$v") -Recurse -Force
}

# ---- -Inventory (1.6.0, 2026-10-04) ---------------------------------------
# Stat-only fleet inventory: JSON Lines on stdout, nothing written anywhere.
function Inv([hashtable]$extra) {
  $cargs = @{ Root = $Root; Inventory = $true; Quiet = $true }
  foreach ($k in $extra.Keys) { $cargs[$k] = $extra[$k] }
  $global:LASTEXITCODE = 0
  $script:invLines = @(& $Collector @cargs 2>$null | ForEach-Object { [string]$_ })
  $script:rc = $LASTEXITCODE
  $script:inv = @($script:invLines | ForEach-Object { $_ | ConvertFrom-Json })
}
function InvAgent([string]$user, [string]$agent) { return ($script:inv | Where-Object { $_.type -eq 'agent' } | Where-Object { $_.user -eq $user -and $_.agent -eq $agent } | Select-Object -First 1) }
# The raw line, for the timestamps: PowerShell 7's ConvertFrom-Json turns ISO strings into DateTime.
function InvRaw([string]$user, [string]$agent) { return ($script:invLines | Where-Object { $_.Contains('"user":"' + $user + '","agent":"' + $agent + '",') } | Select-Object -First 1) }
$hostKeys = 'type,host,collector,mode,at,users_scanned,users_unreadable,docker_volumes'
$agentKeys = 'type,host,user,agent,files,bytes,first,last,projects,evidence'
[System.IO.File]::SetLastWriteTimeUtc((P 'home/bob/.ollama/history'), (New-Object DateTime 2026, 9, 15, 1, 2, 3, ([DateTimeKind]::Utc)))
# bob's ~/.gemini holds only the nested antigravity-cli entry: no gemini-cli line.
Mk 'home/bob/.gemini/antigravity-cli/conversations/b1.db' 'db'
$invCwd = Join-Path $Out 'invcwd'
New-Item -ItemType Directory -Path $invCwd -Force | Out-Null
Push-Location -LiteralPath $invCwd
Inv @{}
Pop-Location
Check 'Inventory exit 0' { $script:rc -eq 0 }
Check 'Inventory writes nothing in the current directory' { @(Get-ChildItem -LiteralPath $invCwd -Force).Count -eq 0 }
Check 'Inventory first line is the host line, keys in order' { $script:inv[0].type -eq 'host' -and (@($script:inv[0].PSObject.Properties | ForEach-Object { $_.Name }) -join ',') -eq $hostKeys -and $script:inv[0].mode -eq 'image' -and $script:invLines[0] -match '"at":"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"' }
Check 'Inventory host line counts' { $script:inv[0].users_unreadable -eq 0 -and $script:inv[0].docker_volumes -eq 3 -and $script:inv[0].users_scanned -ge 2 }
Check 'Inventory every later line is an agent line, keys in order' { $script:inv.Count -gt 10 -and @($script:inv | Select-Object -Skip 1 | Where-Object { $_.type -ne 'agent' -or (@($_.PSObject.Properties | ForEach-Object { $_.Name }) -join ',') -ne $agentKeys }).Count -eq 0 }
$r = InvAgent 'bob' 'ollama'
Check 'Inventory ollama line: history and manifest, excluded blobs not counted' { $r -and $r.files -eq 2 -and $r.bytes -eq 23 -and (InvRaw 'bob' 'ollama').Contains('"first":"2026-09-14T00:00:00Z","last":"2026-09-15T01:02:03Z"') -and $r.evidence -eq '.ollama' }
$r = InvAgent 'alice' 'claude-code'
Check 'Inventory claude-code evidence in catalog order' { $r -and $r.evidence -eq '.claude,.claude.json*,.claude-*/projects,.claude-*/history.jsonl,.claude-*/.claude.json*,.claude-*/.credentials.json,.claude-*/sessions/*.*.key,.claude-*/daemon/control.key,.claude-*/daemon/roster.json,.claude-*/backups/.claude.json.*,.claude-*/ide/*.lock,.claude-*/bridge-spawn/*/mcp.json,.local/state/claude,.cache/claude,Library/Caches/claude-cli-nodejs,AppData/Local/claude-cli-nodejs/Cache/*,AppData/Local/Temp/claude,Applications/Claude Code URL Handler.app' }
Check 'Inventory first and last set for alice claude-code' { (InvRaw 'alice' 'claude-code') -match '"first":"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ","last":"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ"' }
Check 'Inventory: matched directory with no files of its own gives no line' { $null -eq (InvAgent 'bob' 'gemini-cli') -and ($b = InvAgent 'bob' 'antigravity') -and $b.files -eq 1 -and $b.bytes -eq 2 -and $b.evidence -eq '.gemini/antigravity-cli' }
Check 'Inventory: no agent line has zero files' { -not ($script:inv | Where-Object { $_.type -eq 'agent' } | Where-Object { $_.files -eq 0 }) }
Check 'Inventory projects counted per user' { $r.projects -ge 1 }
Check 'Inventory nested entry claimed from the enclosing agent' { (InvAgent 'alice' 'antigravity').evidence -like '*.gemini/antigravity-cli*' -and (InvAgent 'alice' 'gemini-cli').evidence -eq '.gemini' }
# 2026-10-14 catalog match that is an excluded file (#107): alice's Muse Code
# file count, compared with the -Full inventory's below.
$files107 = -1
$r = InvAgent 'alice' 'muse-code'
if ($r) { $files107 = $r.files }
$r = InvAgent 'docker' 'agent-zero'
Check 'Inventory docker volume line' { $r -and $r.files -eq 7 -and $r.bytes -eq 122 -and $r.projects -eq 0 -and $r.evidence -eq '*a0_usr' }
$r = InvAgent 'docker' 'tabby'
Check 'Inventory rootless docker volume line' { $r -and $r.files -eq 1 -and $r.bytes -eq 22 -and $r.evidence -eq '*tabby*' }
Check 'Inventory shared not inventoried' { -not ($script:inv | Where-Object { $_.type -eq 'agent' } | Where-Object { @('shared', 'project', 'live') -contains $_.agent }) }
# 2026-10-19 Codex projectless output directories (#149)
Check '#149 inventory codex-cli evidence names Documents/Codex' { (InvAgent 'bob' 'codex-cli').evidence -like '*Documents/Codex*' }
Check 'Inventory prints no path below a home' { -not ($script:invLines | Where-Object { $_.Contains($Root) -or $_.Contains($Root.Replace('\', '\\')) }) }
$invO = Join-Path $Out 'inv-o'
Inv @{ OutputDir = $invO }
Check 'Inventory with -OutputDir exit 0' { $script:rc -eq 0 }
Check 'Inventory with -OutputDir creates no output directory' { -not (Test-Path -LiteralPath $invO) }
Inv @{ Full = $true }
Check 'Inventory -Full counts excluded files' { $r = InvAgent 'bob' 'ollama'; $r -and $r.files -eq 3 -and $r.bytes -eq 27 }
# 2026-10-14 catalog match that is an excluded file (#107)
# -Full adds one file for each excl and exclf case of $CasesMuse, plus the
# updater file, which the default inventory must not count either.
$full107 = InvAgent 'alice' 'muse-code'
Check '#107 inventory counts an excluded file match only with --full' { $files107 -ge 0 -and $full107 -and ($full107.files - $files107) -eq (@($CasesMuse | Where-Object { $_ -like 'excl*' }).Count + 1) }
Inv @{ Users = 'bob'; NoDocker = $true }
Check 'Inventory -Users keeps one user' { $a = @($script:inv | Where-Object { $_.type -eq 'agent' }); -not ($a | Where-Object { $_.user -eq 'alice' }) -and ($a | Where-Object { $_.user -eq 'bob' }) }
Check 'Inventory -NoDocker: no volumes, no docker lines' { $script:inv[0].users_scanned -eq 1 -and $script:inv[0].docker_volumes -eq 0 -and -not ($script:inv | Where-Object { $_.type -eq 'agent' } | Where-Object { $_.user -eq 'docker' }) }
# stderr is only observable from a child process: the collector logs through [Console]::Error.
$self = (Get-Process -Id $PID).Path
$errFile = Join-Path $Out 'inv-child.stderr'
$childOut = @(& $self -NoProfile -ExecutionPolicy Bypass -File $Collector -Root $Root -Inventory -OutputDir $invO 2>$errFile)
Check 'Inventory without -Quiet: stdout is pure JSON Lines, log on stderr' { $childOut.Count -gt 10 -and @($childOut | Where-Object { $_ -notmatch '^\{"type":"(host|agent)",' }).Count -eq 0 -and (Get-Content -LiteralPath $errFile -Raw) -match 'User ' }
Check 'Inventory child stdout parses line by line' { @($childOut | Where-Object { $_ -ne '' } | ForEach-Object { try { $null = $_ | ConvertFrom-Json; $true } catch { $false } } | Where-Object { -not $_ }).Count -eq 0 }
# Windows PowerShell 5.1 wraps redirected error-stream text at the console width, so a long path splits across lines.
Check 'Inventory -OutputDir noted on stderr' { ((Get-Content -LiteralPath $errFile -Raw) -replace '\s+', ' ') -match 'NOTE: -Inventory writes nothing; -OutputDir .*inv-o ignored' }
$childQ = @(& $self -NoProfile -ExecutionPolicy Bypass -File $Collector -Root $Root -Inventory -Quiet 2>$errFile)
Check 'Inventory -Quiet leaves stderr empty' { $childQ.Count -gt 10 -and -not ((Get-Content -LiteralPath $errFile -Raw) -match '\S') }
# 2026-10-04 bug round: #29 (the -Users run above left alice out, so run once more)
Inv @{ NoDocker = $true }
$r = InvAgent 'alice' 'pearai'
if ($caseInsensitive) {
  Check '#29 Inventory evidence keeps only the first spelling' { $r -and $r.evidence -clike '*.config/PearAI/User*' -and $r.evidence -cnotlike '*.config/pearai/User*' }
} else {
  Check '#29 Inventory evidence keeps both distinct spellings' { $r -and $r.evidence -clike '*.config/PearAI/User,.config/pearai/User*' }
}
Remove-Item -LiteralPath (P 'home/bob/.gemini') -Recurse -Force
if ($Sep -eq '/' -and (& id -u) -ne '0') {
  New-Item -ItemType Directory -Path (P 'home/carol/.claude') -Force | Out-Null
  & chmod 000 (P 'home/carol')
  Inv @{}
  & chmod 700 (P 'home/carol')
  Check 'Inventory counts the unreadable home' { $script:inv[0].users_unreadable -eq 1 }
  Remove-Item -LiteralPath (P 'home/carol') -Recurse -Force
} else { Write-Output 'note: unreadable home inventory check needs a non-root POSIX host, skipped' }

# ---- live mode without the snapshot (1.6.0) --------------------------------
$lo = Join-Path $Out 'livemode'
New-Item -ItemType Directory -Path $lo -Force | Out-Null
$global:LASTEXITCODE = 0
$null = & $Collector -OutputDir $lo -Quiet -Users 'no-such-user-cac' -NoDocker -NoProjects 2>&1
Check 'live mode exit 0' { $LASTEXITCODE -eq 0 }
$lm = Get-ChildItem -LiteralPath $lo -Filter '*.manifest.jsonl' | Select-Object -First 1
$lj = Get-ChildItem -LiteralPath $lo -Filter '*.collection.json' | Select-Object -First 1
Check 'live mode manifest has no live rows' { $lm -and -not (Select-String -LiteralPath $lm.FullName -SimpleMatch '"agent":"live"') }
Check 'live mode collection.json has hostname and no no_live' { $j = Get-Content -LiteralPath $lj.FullName -Raw | ConvertFrom-Json; $j.hostname -ne '' -and $null -eq $j.options.PSObject.Properties['no_live'] }
Check 'live mode writes no live directory' { -not (Test-Path -LiteralPath (Join-Path $lo 'live')) -and -not (Get-ChildItem -LiteralPath $lo -Filter '.stage-*' -Force) }
Check '-NoLive is no longer a parameter' { $threw = $false; try { & $Collector -NoLive -List | Out-Null } catch { $threw = $true }; $threw }

# ---- -List ----------------------------------------------------------------
Check '-List prints catalog' { @(& $Collector -List | Select-String -SimpleMatch 'claude-code|.claude').Count -ge 1 }
Check '-List prints docker volume table' { @(& $Collector -List | Where-Object { $_ -eq 'agent-zero|*a0_usr' }).Count -eq 1 }

# 2026-10-04 bug round: #31
# collection.json names the archive and archiver actually used, and records
# the project options. A tar that fails, first on PATH, forces a fallback: a
# shell script on POSIX, a copy of where.exe named tar.exe on Windows (it
# rejects -czf with exit 2). With CAC_ARCHIVER=tar,zip the fallback is the
# zip; by default it is the PowerShell tar writer (#72).
$ds = Get-Content -LiteralPath (Get-ChildItem -LiteralPath (Join-Path $Out 'default') -Filter '*.collection.json' | Select-Object -First 1).FullName -Raw
$dj = $ds | ConvertFrom-Json
$defArchive = (Get-ChildItem -LiteralPath (Join-Path $Out 'default') | Where-Object { $_.Name -match '\.(tar\.gz|zip)$' } | Select-Object -First 1).Name
Check '#31 default summary names the archive written' { $dj.archive -eq $defArchive -and (($defArchive -like '*.tar.gz' -and @('tar.exe', 'PowerShell tar writer') -contains $dj.capabilities.archiver) -or ($defArchive -like '*.zip' -and $dj.capabilities.archiver -eq 'ZipFile')) }
Check '#31 default summary: no_projects false, projects empty' { $dj.options.no_projects -eq $false -and $ds -match '"no_projects":\s*false,\s*"projects":\s*\[\s*\]' }
$shim = Join-Path $Work 'shim31'
New-Item -ItemType Directory -Path $shim -Force | Out-Null
$shimOk = $false
if ($env:OS -eq 'Windows_NT') {
  $where = Join-Path $env:SystemRoot 'System32\where.exe'
  if (Test-Path -LiteralPath $where) { Copy-Item -LiteralPath $where -Destination (Join-Path $shim 'tar.exe'); $shimOk = $true }
} else {
  [System.IO.File]::WriteAllText((Join-Path $shim 'tar'), "#!/bin/sh`necho 'tar: broken' >&2`nexit 2`n", (New-Object System.Text.UTF8Encoding $false))
  & chmod +x (Join-Path $shim 'tar'); $shimOk = $true
}
if ($shimOk) {
  $oldPath = $env:PATH
  $env:PATH = $shim + [System.IO.Path]::PathSeparator + $env:PATH
  $p1 = P 'srv/p31-one'; $p2 = P 'srv/p31 two'
  $env:CAC_ARCHIVER = 'tar,zip'
  try { Run 'zip31' @{ Project = @($p1, $p2) } } finally { Remove-Item Env:CAC_ARCHIVER }
  $env:PATH = $oldPath
  Check '#31 zip fallback exit 0, zip written' { $script:rc -eq 0 -and $script:A -and $script:A.Name -like '*.zip' -and @(Get-ChildItem -LiteralPath (Join-Path $Out 'zip31') -Filter '*.tar.gz').Count -eq 0 }
  $zj = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json
  Check '#31 zip fallback: on-disk summary names the zip and ZipFile' { $zj.archive -eq $script:A.Name -and $zj.capabilities.archiver -eq 'ZipFile' }
  Check '#31 zip fallback: archived summary matches on-disk' {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [System.IO.Compression.ZipFile]::OpenRead($script:A.FullName)
    try {
      $e = $z.Entries | Where-Object { $_.FullName -eq 'collection.json' } | Select-Object -First 1
      $rd = New-Object System.IO.StreamReader($e.Open())
      try { $in = $rd.ReadToEnd() } finally { $rd.Dispose() }
    } finally { $z.Dispose() }
    $in -eq [System.IO.File]::ReadAllText($script:S.FullName)
  }
  Check '#31 zip fallback: sidecar names the zip' { (Get-Content -LiteralPath "$($script:A.FullName).sha256").EndsWith('  ' + $script:A.Name) }
  Check '#31 -Project values recorded in options.projects' { $zj.options.no_projects -eq $false -and @($zj.options.projects).Count -eq 2 -and $zj.options.projects[0] -eq $p1 -and $zj.options.projects[1] -eq $p2 }
  Check '#72 zip fallback: notes give the tar exit code' { @($zj.notes | Where-Object { $_ -match '^tar(\.exe)? failed \(exit code 2\); fell back to ZipFile$' }).Count -eq 1 }
  # 2026-10-07 (#72): the same failing tar with the default chain falls back
  # to the PowerShell tar writer, and the summary inside the archive says so.
  $env:PATH = $shim + [System.IO.Path]::PathSeparator + $env:PATH
  try { Run 'writer31' @{ NoDocker = $true } } finally { $env:PATH = $oldPath }
  $wj = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json
  $wl = [System.IO.File]::ReadAllText((Get-ChildItem -LiteralPath (Join-Path $Out 'writer31') -Filter '*.log' | Select-Object -First 1).FullName)
  Check '#72 tar fails: the PowerShell tar writer writes the .tar.gz' { $script:rc -eq 0 -and $script:A.Name -like '*.tar.gz' -and $wj.archive -eq $script:A.Name -and $wj.capabilities.archiver -eq 'PowerShell tar writer' }
  Check '#72 tar fails: notes and log give the exit code' { @($wj.notes | Where-Object { $_ -match '^tar(\.exe)? failed \(exit code 2\); fell back to PowerShell tar writer$' }).Count -eq 1 -and $wl -match '(?m)^tar(\.exe)? failed: exit code 2\r?$' }
  Check '#72 tar fails: the archived summary matches the one on disk' {
    $tw = Read-TarGz $script:A.FullName
    @($tw.members | Where-Object { $_.name -eq './collection.json' -and $_.sha256 -eq (Get-FileHash -LiteralPath $script:S.FullName -Algorithm SHA256).Hash.ToLower() }).Count -eq 1
  }
} else { Write-Output 'note: no where.exe to stand in for tar.exe, zip fallback checks skipped' }
Run 'noproj31' @{ NoProjects = $true }
$ns = Get-Content -LiteralPath $script:S.FullName -Raw
Check '#31 -NoProjects recorded' { ($ns | ConvertFrom-Json).options.no_projects -eq $true -and $ns -match '"no_projects":\s*true,\s*"projects":\s*\[\s*\]' }

# 2026-10-04 bug round: #30
# Symlinks are recreated in the archive with their target string verbatim
# under tar, and kept out of a zip, whose writer would follow them. A separate
# image so the default run's counts and notes stay as they are. On Windows a
# junction, which needs no privilege, gives a reparse point to recreate even
# where symlinks cannot be made; where links cannot be created in the stage
# the row must say so in error and claim no archive_path.
$LRoot = Join-Path $Work 'linkroot'
function LinkP([string]$rel) { return (Join-Path $LRoot ($rel.Replace('/', $Sep))) }
function LinkMk([string]$rel, [string]$content) {
  $p = XP (LinkP $rel)
  [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($p))
  [System.IO.File]::WriteAllText($p, $content, (New-Object System.Text.UTF8Encoding $false))
}
LinkMk 'home/eve/.gemini/antigravity-cli/log/real.log' 'LINK-TARGET-BYTES'
LinkMk 'outside/secret.txt' 'OUTSIDE-BYTES'
$isWin = ($env:OS -eq 'Windows_NT')
$fileLinkOk = $false
# .NET 6+ only, so looked up by reflection; 5.1's New-Item would resolve the
# relative target and refuse the dangling one.
$mkFile = [System.IO.File].GetMethod('CreateSymbolicLink', [Type[]]@([string], [string]))
$mkDir = [System.IO.Directory].GetMethod('CreateSymbolicLink', [Type[]]@([string], [string]))
# Invoke rejects PSObject-wrapped strings, so the arguments are cast.
function MkLink($method, [string]$rel, [string]$target) {
  $a = New-Object 'object[]' 2; $a[0] = [string](XP (LinkP $rel)); $a[1] = $target
  [void]$method.Invoke($null, $a)
}
try {
  if ($null -eq $mkFile -or $null -eq $mkDir) { throw 'no symlink API' }
  MkLink $mkFile 'home/eve/.gemini/antigravity-cli/cli.log' 'log/real.log'
  MkLink $mkFile 'home/eve/.gemini/antigravity-cli/dangling.log' 'log/missing.log'
  MkLink $mkDir 'home/eve/.gemini/antigravity-cli/out' '../../../../outside'
  $fileLinkOk = $true
} catch { Write-Output 'note: symlink creation not permitted here, #30 symlink-in-archive checks skipped' }
$junctionOk = $false
if ($isWin) {
  try { New-Item -ItemType Junction -Path (LinkP 'home/eve/.gemini/antigravity-cli/jn') -Target (LinkP 'outside') -ErrorAction Stop | Out-Null; $junctionOk = $true }
  catch { Write-Output 'note: junction creation failed, #30 junction checks skipped' }
  # A % in the name would be expanded by cmd.exe, so 5.1 must not run mklink for it.
  if ($junctionOk) { New-Item -ItemType Junction -Path (LinkP 'home/eve/.gemini/antigravity-cli/jn%TEMP%x') -Target (LinkP 'outside') | Out-Null }
}
$isDesktop = ($PSVersionTable.PSEdition -eq 'Desktop')
function LRun([string]$name) {
  $o = Join-Path $Out $name
  New-Item -ItemType Directory -Path $o -Force | Out-Null
  $global:LASTEXITCODE = 0
  $script:stdout = & $Collector -Root $LRoot -OutputDir $o -Quiet -NoDocker 2>&1 | Out-String
  $script:rc = $LASTEXITCODE
  $script:M = Get-ChildItem -LiteralPath $o -Filter '*.manifest.jsonl' | Select-Object -First 1
  $script:A = Get-ChildItem -LiteralPath $o | Where-Object { $_.Name -match '\.(tar\.gz|zip)$' } | Select-Object -First 1
  $script:S = Get-ChildItem -LiteralPath $o -Filter '*.collection.json' | Select-Object -First 1
  $script:Rows = @()
  if ($script:M) { $script:Rows = @(Get-Content -LiteralPath $script:M.FullName | ForEach-Object { $_ | ConvertFrom-Json }) }
  $script:LSum = $null
  if ($script:S) { $script:LSum = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json }
}
# Bytes of every regular file in the archive, concatenated, to show that no
# link target's content was pulled in.
function ArchiveText {
  $x = Join-Path $Work ('lx-' + [guid]::NewGuid().ToString('N').Substring(0, 6))
  New-Item -ItemType Directory -Path $x -Force | Out-Null
  if ($script:A.Name -like '*.tar.gz') { & tar -xzf $script:A.FullName -C $x 2>$null } else { [System.IO.Compression.ZipFile]::ExtractToDirectory($script:A.FullName, $x) }
  $t = ''
  foreach ($f in @(Get-ChildItem -LiteralPath $x -Recurse -Force -File | Where-Object { ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0 })) { $t += [System.IO.File]::ReadAllText($f.FullName) }
  return $t
}
function LinkRowsConsistent {
  $bad = @($script:Rows | Where-Object { $_.status -eq 'symlink' -and -not (($_.archive_path -ne '') -xor ($_.error -ne '')) })
  return ($bad.Count -eq 0)
}

if ($fileLinkOk -or $junctionOk) {
  # The same checks for tar and, forced with CAC_ARCHIVER, for the
  # PowerShell tar writer (#72), which stores the target as staged.
  foreach ($lrun in @('links-tar', 'links-writer')) {
    $tag = ''
    if ($lrun -eq 'links-writer') { $tag = ' [writer]'; $env:CAC_ARCHIVER = 'writer' }
    try { LRun $lrun } finally { if ($lrun -eq 'links-writer') { Remove-Item Env:CAC_ARCHIVER } }
    Check ('#30 tar run exit 0' + $tag) { $script:rc -eq 0 }
    Check ('#30 every symlink row has archive_path or error, not both' + $tag) { LinkRowsConsistent }
    $tv = @()
    if ($script:A.Name -like '*.tar.gz') { $tv = @(& tar -tvzf $script:A.FullName 2>$null) }
    if ($fileLinkOk) {
      $r = Row 'antigravity-cli/cli.log'
      Check ('#30 symlink row has archive_path and no error' + $tag) { $r -and $r.status -eq 'symlink' -and $r.archive_path -match '^fs/.*antigravity-cli/cli\.log$' -and $r.error -eq '' }
      Check ('#30 archive stores the link with its relative target verbatim' + $tag) { @($tv | Where-Object { $_ -match '^l' -and $_ -match 'antigravity-cli/cli\.log -> log/real\.log$' }).Count -eq 1 }
      Check ('#30 dangling symlink stored as a link' + $tag) { @($tv | Where-Object { $_ -match '^l' -and $_ -match 'antigravity-cli/dangling\.log -> log/missing\.log$' }).Count -eq 1 }
      Check ('#30 directory symlink stored as a link, not descended' + $tag) { @($tv | Where-Object { $_ -match '^l' -and $_ -match 'antigravity-cli/out -> \.\./\.\./\.\./\.\./outside$' }).Count -eq 1 -and -not ($tv | Where-Object { $_ -match 'antigravity-cli/out/' }) }
      Check ('#30 link target bytes outside the collection not archived' + $tag) { (ArchiveText) -notmatch 'OUTSIDE-BYTES' }
      Check ('#30 staging removed and link targets intact' + $tag) { -not (Get-ChildItem -LiteralPath (Join-Path $Out $lrun) -Filter '.stage-*' -Force) -and (Test-Path -LiteralPath (LinkP 'outside/secret.txt')) -and (Test-Path -LiteralPath (LinkP 'home/eve/.gemini/antigravity-cli/log/real.log')) }
    }
    if ($junctionOk) {
      $r = Row 'antigravity-cli/jn'
      Check ('#30 junction row has archive_path or a reason' + $tag) { $r -and $r.status -eq 'symlink' -and (($r.archive_path -ne '' -and $r.error -eq '') -or ($r.archive_path -eq '' -and $r.error -like 'not recreated in the archive:*')) }
      Check ('#30 junction failure noted in collection.json' + $tag) { $r.archive_path -ne '' -or @($script:LSum.notes | Where-Object { $_ -like '*could not be recreated in the archive*' }).Count -eq 1 }
      Check ('#30 junction target bytes not archived' + $tag) { (ArchiveText) -notmatch 'OUTSIDE-BYTES' }
      Check ('#30 junction target intact after staging cleanup' + $tag) { Test-Path -LiteralPath (LinkP 'outside/secret.txt') }
      if ($isDesktop) {
        Check ('#30 5.1: a failed mklink reports its message and exit code' + $tag) { $r.archive_path -ne '' -or $r.error -match '\(mklink exit \d+\)$' }
        $r = Row 'antigravity-cli/jn%TEMP%x'
        Check ('#30 5.1: a % in the link path is refused before cmd.exe' + $tag) { $r -and $r.archive_path -eq '' -and $r.error -like '*contains % or "*' }
      }
    }
    if ($lrun -eq 'links-writer') { Check '#72 links-writer: archiver PowerShell tar writer' { $script:LSum.capabilities.archiver -eq 'PowerShell tar writer' -and $script:A.Name -like '*.tar.gz' } }
  }

  # zip from the start, forced with CAC_ARCHIVER (with no tar on the PATH the
  # PowerShell tar writer is used, #72)
  $savedPath = $env:PATH
  $env:CAC_ARCHIVER = 'zip'
  try { LRun 'links-zip' } finally { Remove-Item Env:CAC_ARCHIVER }
  Check '#30 zip run exit 0 and wrote a zip' { $script:rc -eq 0 -and $script:A.Name -like '*.zip' }
  Check '#30 zip: symlink rows have no archive_path and say zip' { $l = @($script:Rows | Where-Object { $_.status -eq 'symlink' }); $l.Count -ge 1 -and @($l | Where-Object { $_.archive_path -ne '' -or $_.error -notlike '*zip cannot store symlinks*' }).Count -eq 0 }
  Check '#30 zip: collection.json notes say symlinks are manifest-only' { @($script:LSum.notes | Where-Object { $_ -like '*in the manifest only: the zip archive cannot store symlinks*' }).Count -eq 1 }
  Check '#30 zip: no link target content in the zip' { $t = ArchiveText; $t -notmatch 'OUTSIDE-BYTES' -and ([regex]::Matches($t, 'LINK-TARGET-BYTES')).Count -eq 1 }

  # tar fails late: a tar on PATH that exits 1, then the zip fall back,
  # with the PowerShell tar writer left out of the chain by CAC_ARCHIVER
  if (-not $isWin) {
    $shim = Join-Path $Work 'badtar'
    New-Item -ItemType Directory -Path $shim -Force | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $shim 'tar'), "#!/bin/sh`nexit 1`n")
    & chmod +x (Join-Path $shim 'tar')
    $env:PATH = $shim
    $env:CAC_ARCHIVER = 'tar,zip'
    try { LRun 'links-late' } finally { $env:PATH = $savedPath; Remove-Item Env:CAC_ARCHIVER }
    Check '#30 late fallback exit 0 and wrote a zip' { $script:rc -eq 0 -and $script:A.Name -like '*.zip' }
    Check '#30 late fallback: symlink rows rewritten without archive_path' { $l = @($script:Rows | Where-Object { $_.status -eq 'symlink' }); $l.Count -ge 1 -and @($l | Where-Object { $_.archive_path -ne '' -or $_.error -notlike '*tar failed and zip cannot store symlinks*' }).Count -eq 0 }
    Check '#30 late fallback: manifest in the zip matches the one on disk' {
      $z = [System.IO.Compression.ZipFile]::OpenRead($script:A.FullName)
      try { $e = $z.GetEntry('manifest.jsonl'); $rd = New-Object System.IO.StreamReader($e.Open()); $inZip = $rd.ReadToEnd(); $rd.Close() } finally { $z.Dispose() }
      $inZip -eq [System.IO.File]::ReadAllText($script:M.FullName)
    }
    Check '#30 x #31 late fallback: collection.json in the zip matches the one on disk and names the zip' {
      $z = [System.IO.Compression.ZipFile]::OpenRead($script:A.FullName)
      try { $e = $z.GetEntry('collection.json'); $rd = New-Object System.IO.StreamReader($e.Open()); $inZip = $rd.ReadToEnd(); $rd.Close() } finally { $z.Dispose() }
      $inZip -eq [System.IO.File]::ReadAllText($script:S.FullName) -and $script:LSum.archive -eq $script:A.Name -and $script:LSum.capabilities.archiver -eq 'ZipFile'
    }
    Check '#30 late fallback: collection.json notes the removed links' { @($script:LSum.notes | Where-Object { $_ -like 'tar failed;*removed from the staging tree before zipping*' }).Count -eq 1 }
    Check '#30 late fallback: no link target content in the zip' { $t = ArchiveText; $t -notmatch 'OUTSIDE-BYTES' -and ([regex]::Matches($t, 'LINK-TARGET-BYTES')).Count -eq 1 }
    Check '#30 late fallback: link targets intact' { Test-Path -LiteralPath (LinkP 'outside/secret.txt') }
  }
}

# 2026-10-04 bug round: #32, #38, #39
# A relative -Project is resolved against the current location (image mode
# too); a -Project that does not exist gets an error_read row and a log line.
Mk 'srv/relproj/AGENTS.md' '# rel'
$missingProj = Join-Path $Work 'nonexistent-cac'
$prevLoc = Get-Location
Set-Location -LiteralPath (P 'srv')
Run 'projargs' @{ Project = @('relproj', $missingProj) }
Set-Location -LiteralPath $prevLoc.Path
$sum = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json
Check '-Project arguments exit 0' { $script:rc -eq 0 }
Check 'relative -Project resolved against the current location' { (StatusOf 'srv/relproj/AGENTS.md') -eq 'collected' -and @($sum.projects | Where-Object { $_ -eq (P 'srv/relproj') }).Count -eq 1 }
Check '#31 x #39 options.projects records the resolved -Project values' { @($sum.options.projects).Count -eq 2 -and $sum.options.projects[0] -eq (P 'srv/relproj') -and $sum.options.projects[1] -eq $missingProj }
$mr = @($script:Rows | Where-Object { $_.path -eq $missingProj })
Check 'missing -Project gets one error_read dir row' { $mr.Count -eq 1 -and $mr[0].status -eq 'error_read' -and $mr[0].type -eq 'dir' -and $mr[0].home -eq $missingProj -and $mr[0].agent -eq '' -and $mr[0].archive_path -eq '' -and $mr[0].error -ne '' }
$plog = Get-ChildItem -LiteralPath (Join-Path $Out 'projargs') -Filter '*.log' | Select-Object -First 1
Check 'missing -Project logged' { (Get-Content -LiteralPath $plog.FullName -Raw).Contains("WARNING: project given with -Project is not a directory: ${missingProj}: ") }
Check 'missing -Project not listed in projects' { @($sum.projects | Where-Object { $_ -like '*nonexistent-cac*' }).Count -eq 0 }
Check 'missing -Project counted as error_read' { $sum.counts.error_read -eq 1 -and $script:stdout -match '(?m)^errors:     1 \(0 error_copy, 1 error_read\)\s*$' }
$dsum = Get-Content -LiteralPath (Get-ChildItem -LiteralPath (Join-Path $Out 'default') -Filter '*.collection.json' | Select-Object -First 1).FullName -Raw | ConvertFrom-Json
Check 'default run has no error_read rows' { $dsum.counts.error_read -eq 0 }
Remove-Item -LiteralPath (P 'srv/relproj') -Recurse -Force

# A read-only output directory exits 2 before any collection work: chmod on
# POSIX (not as root), a deny ACE for creating files on Windows.
$ro = Join-Path $Out 'readonly'
New-Item -ItemType Directory -Path $ro -Force | Out-Null
$roSet = $false
if ($Sep -eq '/') {
  if ((& id -u) -ne '0') { & chmod 555 $ro; $roSet = $true }
} else {
  $acl = Get-Acl -LiteralPath $ro
  $denyRule = New-Object System.Security.AccessControl.FileSystemAccessRule([Security.Principal.WindowsIdentity]::GetCurrent().User, 'CreateFiles, AppendData', 'Deny')
  $acl.AddAccessRule($denyRule); Set-Acl -LiteralPath $ro -AclObject $acl; $roSet = $true
}
if ($roSet) {
  # Start-Process writes the child's stderr to the file as is. With 2> the
  # 5.1 parent wraps each stderr line in a NativeCommandError record, and its
  # position and category lines land inside a message the child wrapped at
  # the console width (#42). Whitespace is stripped before matching, so a
  # wrap anywhere in the message or the path still matches.
  $roErr = Join-Path $Out 'readonly.stderr'
  $roArgs = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Root "{1}" -OutputDir "{2}" -Quiet -NoDocker' -f $Collector, $Root, $ro
  $roProc = Start-Process -FilePath $self -ArgumentList $roArgs -NoNewWindow -PassThru -RedirectStandardError $roErr -RedirectStandardOutput (Join-Path $Out 'readonly.stdout')
  $null = $roProc.Handle; $roProc.WaitForExit(); $roRc = $roProc.ExitCode
  if ($Sep -eq '/') { & chmod 755 $ro } else { $acl = Get-Acl -LiteralPath $ro; [void]$acl.RemoveAccessRule($denyRule); Set-Acl -LiteralPath $ro -AclObject $acl }
  $roText = (Get-Content -LiteralPath $roErr -Raw) -replace '\s', ''
  $roWant = ('Output dir not writable: ' + $ro) -replace '\s', ''
  Check 'read-only output dir exits 2 before collecting' { $roRc -eq 2 -and $roText.Contains($roWant) -and @(Get-ChildItem -LiteralPath $ro -Force).Count -eq 0 }
} else { Write-Output 'note: read-only output dir check needs a non-root user on POSIX, skipped' }
# 2026-10-14 output directory under a file (#108): the one error, written
# by Write-Error (whitespace stripped as above), with no Resolve-Path or
# StrictMode error and no writability message after it.
$out108 = Join-Path $file108 'out'
$err108 = Join-Path $Out 'file108.stderr'
$args108 = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Root "{1}" -OutputDir "{2}" -Quiet -NoDocker' -f $Collector, $Root, $out108
$proc108 = Start-Process -FilePath $self -ArgumentList $args108 -NoNewWindow -PassThru -RedirectStandardError $err108 -RedirectStandardOutput (Join-Path $Out 'file108.stdout')
$null = $proc108.Handle; $proc108.WaitForExit()
$text108 = [string](Get-Content -LiteralPath $err108 -Raw) -replace '\s', ''
$want108 = ('Cannot create output dir: ' + $out108) -replace '\s', ''
Check '#108 output dir under a file exits 2 with only the create error' { $proc108.ExitCode -eq 2 -and $text108.Contains($want108) -and ($text108.Length - $text108.Replace('Cannotcreateoutputdir', '').Length) -eq 'Cannotcreateoutputdir'.Length -and $text108 -notmatch 'Resolve-Path|ProviderPath|Outputdirnotwritable' -and [System.IO.File]::Exists($file108) }
# 2026-10-14 exclusion globs and the working directory (#109)
Push-Location -LiteralPath $cwd109
try { Run 'cwd109' @{ NoDocker = $true; NoProjects = $true } } finally { Pop-Location }
Check '#109 wildcard exclusion holds from a directory with a matching tree' { $script:rc -eq 0 -and (StatusOf 'Users/alice/.claude/plugins/y/node_modules') -eq 'skipped_excluded' -and -not ($script:Rows | Where-Object { ($_.path -replace '\\', '/') -like '*node_modules/f.js' }) }
# 2026-10-14 CDPATH in the environment (#110): sh only, PowerShell has no
# CDPATH; the check is in smoke.sh.

# An unreadable home and an unlistable directory inside a walk: POSIX and not
# root only, since chmod does not deny on Windows or to root.
if ($Sep -eq '/' -and (& id -u) -ne '0') {
  New-Item -ItemType Directory -Path (P 'home/erin/.claude') -Force | Out-Null
  Mk 'Users/alice/.claude/locked/f' 'x'
  & chmod 000 (P 'home/erin') (P 'Users/alice/.claude/locked')
  Run 'readperm' @{}
  & chmod 700 (P 'home/erin') (P 'Users/alice/.claude/locked')
  $sum = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json
  Check 'unreadable paths exit 0' { $script:rc -eq 0 }
  $er = @($script:Rows | Where-Object { $_.path -eq (P 'home/erin') })
  Check 'unreadable home gets one error_read row' { $er.Count -eq 1 -and $er[0].status -eq 'error_read' -and $er[0].user -eq 'erin' -and $er[0].agent -eq '' -and $er[0].type -eq 'dir' -and $er[0].size -eq 0 -and $er[0].archive_path -eq '' -and $er[0].error -match 'denied' }
  Check 'unreadable home stays in users, not in users_with_artifacts' { @($sum.users) -contains 'erin' -and -not (@($sum.users_with_artifacts) -contains 'erin') }
  $lr = Row 'Users/alice/.claude/locked'
  Check 'unlistable directory in a walk gets an error_read row' { $lr -and $lr.status -eq 'error_read' -and $lr.agent -eq 'claude-code' -and $lr.type -eq 'dir' -and $lr.error -match 'denied' }
  Check 'rest of the home still collected' { (StatusOf 'Users/alice/.claude/projects/-C-proj/s1.jsonl') -eq 'collected' }
  Check 'unreadable paths counted' { $sum.counts.error_read -eq 2 -and $script:stdout -match '(?m)^errors:     2 \(0 error_copy, 2 error_read\)\s*$' }
  Remove-Item -LiteralPath (P 'home/erin'), (P 'Users/alice/.claude/locked') -Recurse -Force
} else { Write-Output 'note: unreadable home and directory checks need a non-root POSIX host, skipped' }

# 2026-10-04 bug round: #29 x #32
# An unreadable catalog match gets one error_read row, and a case variant
# folded into it (case-insensitive filesystem) gets none of its own: chmod on
# POSIX (not as root), a deny ACE for listing on Windows.
$fd = P 'Users/alice/.config/pearai/User'
$fdSet = $false
# An enabled SeBackupPrivilege (an administrator's token in a Windows OpenSSH
# session) lets the listing through the deny ACE, so the block is skipped
# there, as it is for root on POSIX; on CI the privilege is present but
# disabled. Read from whoami /priv, whose last column is the state.
$backupPriv = $false
if ($Sep -ne '/') {
  try { $backupPriv = @(& whoami.exe /priv 2>$null | Where-Object { $_ -match '^\s*SeBackupPrivilege\s.*\sEnabled\s*$' }).Count -gt 0 } catch { }
}
if ($Sep -eq '/') {
  if ((& id -u) -ne '0') { & chmod 000 $fd; $fdSet = $true }
} elseif ($backupPriv) {
  Write-Output 'note: SeBackupPrivilege is enabled in this session and bypasses the deny ACE, #29 x #32 unreadable case-variant check skipped'
} else {
  $fdAcl = Get-Acl -LiteralPath $fd
  $fdRule = New-Object System.Security.AccessControl.FileSystemAccessRule([Security.Principal.WindowsIdentity]::GetCurrent().User, 'ListDirectory', 'Deny')
  $fdAcl.AddAccessRule($fdRule); Set-Acl -LiteralPath $fd -AclObject $fdAcl; $fdSet = $true
}
if ($fdSet) {
  try { Run 'fold32' @{ NoDocker = $true } }
  finally {
    if ($Sep -eq '/') { & chmod 755 $fd } else { $fdAcl = Get-Acl -LiteralPath $fd; [void]$fdAcl.RemoveAccessRule($fdRule); Set-Acl -LiteralPath $fd -AclObject $fdAcl }
  }
  $fsum = Get-Content -LiteralPath $script:S.FullName -Raw | ConvertFrom-Json
  $fr = @($script:Rows | Where-Object { $_.status -eq 'error_read' -and ($_.path -replace '\\', '/').ToLowerInvariant().EndsWith('/.config/pearai/user') })
  Check '#29 x #32 unreadable case-variant match: exactly one error_read row' { $script:rc -eq 0 -and $fr.Count -eq 1 -and $fsum.counts.error_read -eq 1 }
  if ($caseInsensitive) {
    Check '#29 x #32 folded variant has no rows of its own' { @($script:Rows | Where-Object { ($_.path -replace '\\', '/').ToLowerInvariant() -like '*/.config/pearai/user*' }).Count -eq 1 }
  } else {
    Check '#29 x #32 the readable spelling is still collected' { (HasPath 'Users/alice/.config/PearAI/User/case29-upper.json') }
  }
} elseif ($Sep -eq '/') { Write-Output 'note: #29 x #32 unreadable case-variant check needs a non-root user on POSIX, skipped' }

# 2026-10-10 Claude Desktop MSIX build (#73)
# The MSIX build keeps userData in the package's virtualised
# LocalCache\Roaming\Claude, logs in AppData\Local\Claude\logs, and may use
# AppData\Local\Claude-Data\<family>. A separate image holds one Windows
# profile with those trees; the */Claude*/ secret and exclusion globs must
# apply under the new bases, and the Packages secret globs must flag the
# token cache and cookies of both package families.
$script:Made.Clear()
$root73 = $Root
$Root = Join-Path $Work 'root73'
$p73 = 'Users/alice/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Roaming/Claude'
$q73 = 'Users/alice/AppData/Local/Packages/AnthropicPBC.Claude_fnn82j28hfe8t/LocalCache/Roaming/Claude'
$o73 = '11111111-1111-4111-8111-111111111111/22222222-2222-4222-8222-222222222222'
$s73 = "$p73/claude-code-sessions/$o73/local_44444444-4444-4444-8444-444444444444.json"
$k73 = "$p73/local-agent-mode-sessions/$o73/local_33333333-3333-4333-8333-333333333333/.audit-key"
$r73 = "$p73/local-agent-mode-sessions/$o73/remote-session-spaces.json"
$d73 = 'Users/alice/AppData/Local/Claude-Data/claude_pzs8sxrjxfjjc/config.json'
$l73 = 'Users/alice/AppData/Local/Claude/logs/main.log'
Mk "$p73/config.json" '{"oauth:tokenCache":"enc"}'
Mk "$p73/Local State" '{"os_crypt":{}}'
Mk "$p73/claude_desktop_config.json" '{"mcpServers":{}}'
Mk "$p73/Network/Cookies" 'cookies'
Mk $s73 '{"sessionId":"local_44444444-4444-4444-8444-444444444444","cwd":"C:\\proj"}'
Mk $r73 '{"entries":[{"sessionId":"0123456789abcdef0123456789abcdef","folders":[]}]}'
Mk $k73 'key'
Mk "$p73/claude-code/2.1.295/abc/claude.exe" 'MZ'
Mk "$p73/Cache/data_0" 'cache'
Mk "$q73/config.json" '{"oauth:tokenCache":"enc"}'
Mk $l73 '[MSIX] Filesystem virtualization active'
Mk $d73 '{"oauth:tokenCache":"enc"}'
$Miss = Test-Made
Check "#73 every MSIX build fixture was created ($($Miss.Count) missing$(if ($Miss.Count) { ', first ' + $Miss[0] }))" { $Miss.Count -eq 0 }
function Secret73([string]$rel) { $r = Row $rel; return ($r -and $r.agent -eq 'claude-desktop' -and $r.secret -eq $true -and $r.status -eq 'collected') }
function Plain73([string]$rel) { $r = Row $rel; return ($r -and $r.agent -eq 'claude-desktop' -and $r.secret -eq $false -and $r.status -eq 'collected') }
try {
  Run 'store73' @{ NoDocker = $true }
  Check '#73 MSIX build run exit 0' { $script:rc -eq 0 }
  Check '#73 Packages Code-tab session record collected as claude-desktop' { Plain73 $s73 }
  Check '#73 Packages session record collected exactly once' { @($script:Rows | Where-Object { $_.path -like '*local_44444444-4444-4444-8444-444444444444.json' }).Count -eq 1 }
  Check '#73 Packages remote-session-spaces.json collected' { Plain73 $r73 }
  Check '#73 AppData/Local/Claude logs collected as claude-desktop' { Plain73 $l73 }
  Check '#73 Packages config.json flagged secret (Packages/Claude_* glob)' { Secret73 "$p73/config.json" }
  Check '#73 Packages Network/Cookies flagged secret (Packages/Claude_* glob)' { Secret73 "$p73/Network/Cookies" }
  Check '#73 AnthropicPBC family config.json flagged secret' { Secret73 "$q73/config.json" }
  Check '#73 Claude-Data config.json flagged secret (AppData/Local/Claude* glob)' { Secret73 $d73 }
  Check '#73 Packages Local State flagged secret (*/Claude*/Local State)' { Secret73 "$p73/Local State" }
  Check '#73 Packages claude_desktop_config.json flagged secret (*/Claude*/claude_desktop_config.json)' { Secret73 "$p73/claude_desktop_config.json" }
  Check '#73 Packages .audit-key flagged secret (*/Claude*/local-agent-mode-sessions/*/.audit-key)' { Secret73 $k73 }
  Check '#73 Packages claude-code excluded (*/Claude*/claude-code)' { (StatusOf "$p73/claude-code") -eq 'skipped_excluded' -and -not (Row "$p73/claude-code/2.1.295/abc/claude.exe") }
  Check '#73 Packages Cache excluded (*/Claude*/Cache)' { (StatusOf "$p73/Cache") -eq 'skipped_excluded' -and -not (Row "$p73/Cache/data_0") }
  Run 'nosecrets73' @{ NoDocker = $true; NoSecrets = $true }
  Check '#73 NoSecrets run exit 0' { $script:rc -eq 0 }
  Check '#73 NoSecrets skips the Packages and Claude-Data token caches' { (StatusOf "$p73/config.json") -eq 'skipped_secret' -and (StatusOf "$q73/config.json") -eq 'skipped_secret' -and (StatusOf $d73) -eq 'skipped_secret' }
  Check '#73 NoSecrets skips Local State, claude_desktop_config.json, .audit-key' { (StatusOf "$p73/Local State") -eq 'skipped_secret' -and (StatusOf "$p73/claude_desktop_config.json") -eq 'skipped_secret' -and (StatusOf $k73) -eq 'skipped_secret' }
  Check '#73 NoSecrets still collects the session record' { (StatusOf $s73) -eq 'collected' }
  Run 'full73' @{ NoDocker = $true; Full = $true }
  Check '#73 Full run exit 0' { $script:rc -eq 0 }
  Check '#73 Full collects the Packages claude.exe and Cache' { (StatusOf "$p73/claude-code/2.1.295/abc/claude.exe") -eq 'collected' -and (StatusOf "$p73/Cache/data_0") -eq 'collected' }
} finally { $Root = $root73 }

if ($script:fail -eq 0) { Write-Output "ALL PASSED ($($PSVersionTable.PSEdition) $($PSVersionTable.PSVersion))"; Remove-Item -LiteralPath (XP $Work) -Recurse -Force -ErrorAction SilentlyContinue }
else { Write-Output "FAILURES; work dir kept: $Work" }
exit $script:fail
