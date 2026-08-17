# scripts/

Interactive helper suite for operating a Brane deployment from your local machine.

---

## Entry point

```bash
bash scripts/brane_main.sh
```

On launch, the helper reads `hosts.ini` and scans the repo for `packages/`, `datasets/`,
`policies/`, `certs/`, and `policy_tokens/`, then presents a snapshot and asks you to
select a role.

---

## Scripts

| Script | Purpose |
|---|---|
| `brane_main.sh` | Entry point — welcome screen, infra snapshot, role selector |
| `brane_lib.sh` | Shared library — logging, config, port checks, common helpers |
| `brane_helper_user.sh` | User role — packages, certificates, instances, workflows |
| `brane_helper_admin.sh` | Admin role — Ansible deployment, health checks, cleanup |
| `brane_helper_policy.sh` | Policy Manager role — add and activate eFLINT policies |
| `brane_gen_cert.sh` | Generate client certificates signed by a node CA |
| `brane_healthcheck.sh` | Verify central/worker containers, ports, and volume mounts |
| `clean_central_worker.sh` | Remote cleanup of Docker resources and deployment dirs |
| `package_build_macOS.sh` | Build Brane packages targeting x86_64 from an Apple Silicon Mac |

### Supporting directories

| Path | Purpose |
|---|---|
| `smoke-test/` | End-to-end smoke tests (also triggered by Ansible `--tags smoke`) |
| `templates/` | Docker Compose templates used by the Ansible `brane_deploy` role |

---

## Configuration

Copy the example config once and edit it with your environment values:

```bash
cp scripts/.brane_helper.env.example scripts/.brane_helper.env
$EDITOR scripts/.brane_helper.env
```

`.brane_helper.env` is git-ignored and must never be committed.

