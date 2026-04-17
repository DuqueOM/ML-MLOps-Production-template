#!/usr/bin/env bash
# Detects the operating system for conditional installation.
# Exports OS variable: linux | macos | wsl | unsupported

detect_os() {
  case "$(uname -s)" in
    Linux*)
      if grep -qi microsoft /proc/version 2>/dev/null; then
        echo "wsl"
      else
        echo "linux"
      fi
      ;;
    Darwin*) echo "macos" ;;
    *)       echo "unsupported" ;;
  esac
}
