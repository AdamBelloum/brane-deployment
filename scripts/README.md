i# scripts/

Helper scripts for operating a Brane deployment from your local control machine.

---

## Scripts overview

| Script                            | Purpose                                                         |
|-----------------------------------|-----------------------------------------------------------------|
| `brane_helper.sh`                 | Interactive menu: Ansible deployment + Brane CLI operations     |
| `brane_cleanup.sh`                | Tear down and clean up Brane containers and data on remote VMs  |
| `clean_central_worker.sh`         | Reset central and worker nodes to a clean state                 |
| `troubleshoot-brane-deployment.sh`| Diagnostic checks for a running or broken deployment            |
| `package_build_macOS.sh`          | Build a Brane package on macOS (Docker-in-Docker workaround)    |
| `show_brane_tools_help.sh`        | Print help for all Brane CLI subcommands                        |
| `smoke-test/`                     | Smoke test scripts run after deployment to verify the cluster   |
| `templates/`                      | Docker Compose templates for central and worker nodes           |

---

## brane_helper.sh

The main interactive helper. It wraps both Ansible playbook execution and Brane CLI commands in a numbered menu.

### Setup (one-time)

```bash
# 1. Copy the example config
cp scripts/.brane_helper.env.example scripts/.brane_helper.env

# 2. Edit it with your values (IPs, domain, paths)
$EDITOR scripts/.brane_helper.env
```

The `.brane_helper.env` file is **git-ignored** and must never be committed.

### Running

```bash
bash scripts/brane_helper.sh
```

You can also point to a different config file via an environment variable:

```bash
BRANE_HELPER_CONFIG=/path/to/my.env bash scripts/brane_helper.sh
```

### Config variables

| Variable          | Required | Default                           | Description                                  |
|-------------------|----------|-----------------------------------|----------------------------------------------|
| `HOST_IP`         | Yes      | —                                 | IP of the central hub VM                     |
| `INSTANCE_DOMAIN` | Yes      | —                                 | FQDN of the central hub (for `brane instance add`) |
| `BRANE_DEPLOY_HOME` | No     | `<repo>/docker-deployment`        | Path to the docker-deployment directory      |
| `PACKAGE_DIR`     | No       | `<repo>/frontend/packages`        | Path to the Brane packages directory         |
| `PORT_REPL`       | No       | `50053`                           | Brane REPL port                              |
| `PORT_REGISTRY`   | No       | `50051`                           | Brane registry port                          |
| `INSTANCE_NAME`   | No       | `my-brane`                        | Local alias for the Brane instance           |
| `PACKAGE_NAME`    | No       | `hello_world`                     | Default package name for CLI operations      |
| `PACKAGE_VERSION` | No       | `1.0.0`                           | Default package version for push             |

---

## troubleshoot-brane-deployment.sh

Run this when a deployment is failing or a node is misbehaving. It collects:

- Docker container status on each node
- Brane service logs
- Network connectivity between nodes

```bash
bash scripts/troubleshoot-brane-deployment.sh
```

---

## smoke-test/

Contains scripts that verify the cluster is working end-to-end after deployment. These are also triggered by the Ansible `smoke` tag:

```bash
ansible-playbook -i docker-deployment/inventories/production/hosts.ini \
    docker-deployment/site.yml --tags smoke
```

---

## templates/

Docker Compose YAML templates used by Ansible roles to start the central and worker services. These are fetched from GitHub at deploy time via the URLs defined in `docker-deployment/group_vars/all.yml`.

---

## Security note

- `scripts/.brane_helper.env` is in `.gitignore` — **never commit it**.
- Scripts do not store or transmit credentials; all SSH access uses key-based auth managed by Ansible.

