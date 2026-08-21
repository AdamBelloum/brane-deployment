# Release-lock integration validation — 2026-08-21

## Curated implementation revision

- Branch: `feat/release-lock-integration`
- Implementation commit: `4bb5300`
- Base: `origin/main` at `015340f` (`v1.0.0`)

The curated integration includes:

1. deployment, CLI, smoke-test, and cleanup alignment;
2. locked Brane release artefacts;
3. the Tier 1 deployment health gate;
4. parameterised worker service ports.

Unrelated frontend refactoring and documentation-notification CI changes were excluded.

## Local structural validation

The following checks passed:

- `git diff --check origin/main...HEAD`;
- shell parsing with `bash -n` for the health-check, smoke-test, and cleanup scripts;
- Ansible syntax validation of `docker-deployment/site.yml`.

## Runtime health validation

The health check was run from this checkout with inventory
`docker-deployment/inventories/production/hosts.ini`.

- Health report timestamp: `2026-08-21 22:20:05 CEST`
- Central: `central-vm-1` (`145.100.135.209`)
- Workers: `worker-vm-2` (`145.100.135.172`) and `worker-vm-3` (`145.100.135.241`)
- Reported Brane version: `test`
- Result: `133 passed, 0 failed`
- Status: **HEALTHY**

## Provenance limitation

The health check verifies the current remote runtime state, but it does not by
itself prove that the running deployment was deployed from commit `4bb5300`.
A deployment or redeployment record is required for that stronger claim.
