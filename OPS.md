# Operations Guide

This guide provides the essential procedures for managing the deployment, health, and recovery of the Agent Tutor system.

## 1. How to Trigger a Deployment

The deployment process follows a strict **Staging $\rightarrow$ Production** pipeline to prevent regressions.

### Standard Sequence
1. **Push Code**: Push changes to the `master` branch. 
   *Note: On limited-RAM machines, use the bounded push command specified in `AGENTS.md` §3.*
2. **Deploy to Staging**: 
   Trigger the deployment to the staging environment:
   ```bash
   render deploys create srv-db0ip2ugekts739sr36g --confirm
   ```
3. **Verify Staging**: 
   Wait for the status to become `live` and then verify the health probes (see Section 2).
4. **Deploy to Production**: 
   Only after staging is verified green, trigger the production deployment via the Render dashboard or CLI.

## 2. How to Check System Health

A deployment is only considered successful if the following probes return the expected results:

| Probe | Expected Result |
| :--- | :--- |
| `GET /api/health` | HTTP 200; `ollama`, `langgraph`, and `database` must all be `true` |
| Deploy Status | Status `live` and the deployed commit matches the pushed commit |
| CORS | `Access-Control-Allow-Origin` must match the environment's exact origin (never `*`) |
| Auth Check | `POST /api/auth/session` with malformed data must return HTTP 401 with a generic message |

## 3. How to Perform a Rollback

Rollbacks are decisions, not reflexes. Always verify the current system state before restoring a previous version.

### Procedure
1. **Identify Known Good Commit**: Identify the hash of the last stable commit (e.g., `e83a4d5` for Authentication).
2. **Reset/Revert**:
   * For a clean rollback in Git: `git reset --hard <commit_hash>` followed by a forced push (use with caution).
   * Alternatively, use the Render/Vercel dashboards to redeploy a previous successful build.
3. **Verify**: Immediately run the health probes described in Section 2.

## 4. Critical Environment Variables

Variables are managed across three main platforms. **Never log or display secrets in plaintext.**

| Variable Category | Managed In | Description |
| :--- | :--- | :--- |
| **Infrastructure/DB** | Terraform / Neon | `DATABASE_URL`, Neon Branching settings |
| **Backend Secrets** | Render | `APP_ENV`, `API_CORS_ORIGINS`, LLM API Keys (`OPENAI_API_KEY`, etc.), `TAVILY_API_KEY` |
| **Frontend Config** | Vercel | `NEXT_PUBLIC_API_URL`, Vercel Project IDs |

*For a detailed list of variables consumed by the code, refer to `ENV.md` (if available) or perform an execution trace of `os.environ`.*
