  #!/usr/bin/env bash
  set -euo pipefail

  # 1) 确保工作区干净
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Working tree is not clean. Please commit or stash first."
    exit 1
  fi

  # 2) 备份标签（可选，但建议）
  git tag backup/pre-filter-repo-$(date +%Y%m%d_%H%M%S)

  # 3) 安装 git-filter-repo（如果未安装）
  if ! git filter-repo --help >/dev/null 2>&1; then
    echo "git-filter-repo not found, installing to user site..."
    python -m pip install --user git-filter-repo
    # 若需要，提醒用户将 ~/.local/bin 加入 PATH
    if ! command -v git-filter-repo >/dev/null 2>&1; then
      echo "git-filter-repo installed but not in PATH. Try:"
      echo 'export PATH="$HOME/.local/bin:$PATH"'
      exit 1
    fi
  fi

  # 4) 重写历史：只删 tests/fixtures 下的图片
  git filter-repo --force \
    --path-regex '^(tests/fixtures/.*\.(jpg|jpeg|png|heic|heif|webp|tif|tiff|bmp))$' \
    --invert-paths

  # 5) 强推远端（确认远端名/分支）
  git push --force --all
  git push --force --tags

  echo "Done. History rewritten and pushed."