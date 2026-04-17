#!/usr/bin/env bash
# Configures Windsurf MCP servers for this template.
# Non-destructive: preserves existing servers, prompts before overwriting.

configure_mcps() {
  local repo_root="$1"
  local mcp_config="$HOME/.codeium/windsurf/mcp_config.json"

  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 required for MCP config. Skipping."
    return 0
  fi

  # Create config dir if missing
  mkdir -p "$(dirname "$mcp_config")"
  if [[ ! -f "$mcp_config" ]]; then
    echo '{"mcpServers": {}}' > "$mcp_config"
  fi

  echo "This template recommends 4 MCPs:"
  echo "  1. github           (CI logs, PR status)  — requires PAT"
  echo "  2. kubectl-mcp-server (cluster ops)       — requires kubectl"
  echo "  3. terraform-mcp-server (IaC validation)  — requires docker"
  echo "  4. git              (local repo ops)      — requires docker"
  echo ""
  read -rp "Configure these MCPs now? [y/N] " reply
  if [[ ! "$reply" =~ ^[Yy]$ ]]; then
    echo "Skipping MCP setup. You can run this later: ./scripts/bootstrap.sh (it's idempotent)"
    return 0
  fi

  # GitHub MCP
  echo ""
  read -rp "GitHub PAT (scopes: Actions read, Pull requests read) [enter to skip]: " gh_pat
  echo ""

  python3 - "$mcp_config" "$gh_pat" <<'PYEOF'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
gh_pat = sys.argv[2].strip()

config = json.loads(config_path.read_text())
config.setdefault("mcpServers", {})

# Only write kubectl config if the binary is detected; otherwise skip
import shutil
kubectl_bin = shutil.which("kubectl-mcp-serve")
if kubectl_bin:
    config["mcpServers"]["kubectl-mcp-server"] = {
        "command": kubectl_bin,
        "args": ["serve", "--transport", "stdio", "--read-only"],
        "env": {},
    }
    print(f"  ✓ kubectl-mcp-server ({kubectl_bin})")
else:
    print("  ⚠ kubectl-mcp-serve not found on PATH. Install: pip install kubectl-mcp-tool")

# Docker-based MCPs
if shutil.which("docker"):
    projects_dir = str(Path.home() / "projects")
    config["mcpServers"]["git"] = {
        "command": "docker",
        "args": [
            "run", "-i", "--rm",
            "--mount", f"type=bind,src={projects_dir},dst=/projects",
            "mcp/git",
        ],
        "env": {},
    }
    print(f"  ✓ git (docker, mounted {projects_dir})")

    config["mcpServers"]["terraform-mcp-server"] = {
        "command": "docker",
        "args": [
            "run", "-i", "--rm",
            "--mount", f"type=bind,src={projects_dir},dst=/projects",
            "hashicorp/terraform-mcp-server:latest",
        ],
        "env": {},
    }
    print(f"  ✓ terraform-mcp-server (docker)")
else:
    print("  ⚠ docker not found. git and terraform MCPs skipped.")

# GitHub via Streamable HTTP (no local process)
if gh_pat:
    config["mcpServers"]["github"] = {
        "serverUrl": "https://api.githubcopilot.com/mcp/",
        "headers": {"Authorization": f"Bearer {gh_pat}"},
    }
    print("  ✓ github (Streamable HTTP)")
else:
    print("  ⚠ GitHub MCP skipped (no PAT provided)")

config_path.write_text(json.dumps(config, indent=2))
print(f"\nConfig written: {config_path}")
print("→ Restart Windsurf or click 🔄 in the MCP panel to reload.")
PYEOF
}
