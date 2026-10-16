#!/usr/bin/env bash
# Deploy both Vercel projects to production from the repo root.
# (Each project's Root Directory is set in Vercel: backend/ and frontend/. Pushing to main
# also deploys automatically; this script is for deploying without a push.)
# Usage: ./deploy.sh [backend|frontend]   (default: both)
set -euo pipefail
cd "$(dirname "$0")"
for p in ${1:-backend frontend}; do
  org=$(grep -oE '"orgId":"[^"]+"' "$p/.vercel/project.json" | cut -d'"' -f4)
  pid=$(grep -oE '"projectId":"[^"]+"' "$p/.vercel/project.json" | cut -d'"' -f4)
  echo "== deploying $p"
  VERCEL_ORG_ID=$org VERCEL_PROJECT_ID=$pid vercel --prod --yes
done
