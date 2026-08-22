# docker-deployment

Ansible-based automation to deploy a Brane cluster on bare Docker across multiple VMs.

---

## Repository structure

```text
docker-deployment/
├── inventories/
│   └── production/
│       └── hosts.ini            # Target VM IPs and location mappings
├── roles/
│   └── brane_deploy/            # Single unified role with task files
│       └── tasks/
│           ├── prerequisites.yml
│           ├── branectl.yml
│           ├── worker.yml
│           ├── central.yml
│           ├── certs.yml
│           ├── start.yml
│           └── smoke_test.yml
├── group_vars/
│   └── all.yml                  # Global variables (URLs, versions, paths)
├── docs/                        # Troubleshooting guides
├── ansible.cfg                  # Ansible configuration
├── site.yml                     # Master playbook (all stages, tagged)
├── deploy_docker.yml            # Alternative entry-point playbook
├── requirements.txt             # Python/Ansible dependencies
└── test-lint.sh                 # Local lint runner
```

---

## Prerequisites

On your **control machine** (laptop or CI runner):

- Python ≥ 3.10
- Ansible ≥ 2.14
- SSH key-based access to all target VMs

```bash
pip install -r requirements.txt
```
also required Ansible collections
```bash
ansible-galaxy collection install -r requirements.yml --ignore-certs
```

---

## Configuration

### 1. Inventory – `inventories/production/hosts.ini`

Replace the placeholder IPs with your actual VM addresses:

```ini
[central]
hub-vm-1 ansible_host=192.168.1.10 central_ip=192.168.1.10 location_id=central-hub

[workers]
worker-vm-2 ansible_host=192.168.1.11 node_ip=192.168.1.11 location_id=client-node-1 central_ip=192.168.1.10
worker-vm-3 ansible_host=192.168.1.12 node_ip=192.168.1.12 location_id=client-node-2 central_ip=192.168.1.10
```

### 2. Global variables – `group_vars/all.yml`

Key variables to review before running:

| Variable           | Default                  | Description                              |
|--------------------|--------------------------|------------------------------------------|
| `brane_user_home` | `/home/adam` | Home directory of the remote deploy user |
| `ansible_user` | set in inventory | SSH user for all VMs |
| `brane_release` | `test` | Release manifest containing URLs and verified SHA-256 digests |
| `brane_cli_artifacts` | `linux-x86_64` | Checksum-pinned `brane` CLI artefact |
| `branectl_artifacts` | `linux-x86_64` | Checksum-pinned `branectl` artefact |
| `brane_image_tag` | `test` | Local tag applied to images loaded from the locked archives |

> **Note:** `brane_user_home` must match the actual home directory of the SSH user on the target VMs (e.g. `/home/ubuntu` for Ubuntu cloud images).

---

## Running the deployment

### Full deployment (all stages in sequence)

```bash
ansible-playbook -i inventories/production/hosts.ini site.yml
```

### Step-by-step using tags

Run each stage independently. The recommended order is:

```bash
# 1. Install system packages and Docker
ansible-playbook -i inventories/production/hosts.ini site.yml --tags prerequisites

# 2. Download and install branectl + brane CLI
ansible-playbook -i inventories/production/hosts.ini site.yml --tags branectl

# 3. Configure worker nodes
ansible-playbook -i inventories/production/hosts.ini site.yml --tags workers

# 4. Configure central hub
ansible-playbook -i inventories/production/hosts.ini site.yml --tags central

# 5. Generate and exchange mTLS certificates
ansible-playbook -i inventories/production/hosts.ini site.yml --tags certs

# 6. Start all Brane services
ansible-playbook -i inventories/production/hosts.ini site.yml --tags start

# 7. Run smoke test
ansible-playbook -i inventories/production/hosts.ini site.yml --tags smoke
```

### Dry run (check mode)

```bash
ansible-playbook -i inventories/production/hosts.ini site.yml --check --diff
```

### Syntax check

```bash
ansible-playbook -i inventories/production/hosts.ini site.yml --syntax-check
```

---

## Cryptographic key management

The deployment uses an ephemeral CA trust model to avoid persistent key exposure:

1. **CA Initialization** — `ca.pem` and `ca-key.pem` are generated on the Central Hub VM.
2. **Secure Transport** — The CA keypair is fetched to a temporary path (`/tmp/brane_certs`) on the Ansible control machine via encrypted SSH.
3. **Just-in-Time Signing** — The CA assets are pushed to each Worker to sign unique node keypairs locally.
4. **Permanent Purge** — `ca-key.pem` is deleted from Worker nodes and the control machine immediately after signing.

### Key placement summary

| Asset            | Central Hub | Worker Nodes | Risk level         |
|------------------|-------------|--------------|---------------------|
| `ca.pem`         |    Present  |    Present   | Public / Low        |
| `ca-key.pem`     |    Present  |    Purged    | Critical / Confined |
| `worker-key.pem` |    Absent   |    Present   | High / Node-bound   |

---

## Package deployment

To deploy a Brane package, place the package directory under the `brane_package_deployer` role's `files/` folder:

```text
roles/brane_deploy/files/
└── my_package/
    ├── my_function.py     # Source code
    └── container.yml      # Brane interface definition
```

---

## Manual verification

SSH into any node and run:

```bash
# List running Brane containers
docker ps

# Check proxy logs
docker logs brane-proxy

# View central engine logs
cd ~/brane-central && branectl logs
```

---

## Cluster lifecycle

### Stop the cluster

```bash
# On the central hub VM
branectl stop central

# On each worker VM
branectl stop worker
```

### Upgrade Brane images

```bash
# On the central hub VM
branectl download central && branectl start central
```

---

## Troubleshooting

See [`docs/`](docs/) for troubleshooting guides, or run the interactive troubleshoot script:

```bash
bash ../scripts/troubleshoot-brane-deployment.sh
```

## Selecting a Brane release

`group_vars/all.yml` is the deployment’s single release lock. It records a
GitHub release tag, direct asset URLs, and SHA-256 digests. Docker image tags
are derived from `brane_release.tag`; do not set image versions independently.

Use the administrator selector to inspect releases:

```bash
./scripts/select-brane-release.py
```

The selector displays every GitHub release. A release is selectable only when
it supplies the x86_64 CLI and central/worker deployment archives required by
this repository, with published SHA-256 digests.

Preview a prospective release lock without changing anything:

```bash
./scripts/select-brane-release.py --dry-run
```

Selecting the already locked release performs no action. Selecting a different
release requires typing `CLEAN`. The selector then runs:

```bash
ansible-playbook -i inventories/production/hosts.ini site.yml --tags cleanup
```

This removes Brane runtime artefacts on the central and worker nodes, including
Compose resources, named Brane images, generated configuration, certificates,
policy state, downloaded archives, package/data/result directories, and smoke
test output. It preserves this repository, the inventory, SSH configuration,
and source directories such as `packages/`, `certs/`, `datasets/`, `policies/`,
and `policy_tokens/`.

After a successful selection, deploy the locked release normally:

```bash
ansible-playbook -i inventories/production/hosts.ini site.yml
```
