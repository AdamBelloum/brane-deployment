# brane-deployment

Tooling to deploy and operate a [Brane](https://github.com/BraneFramework/brane) distributed computing cluster.

## What is Brane?

Brane is a programmable orchestration framework for distributed data pipelines across federated sites. This repository automates the full lifecycle: infrastructure provisioning, certificate exchange, service startup, and package deployment.

---

## Repository layout

```text
brane-deployment/
├── docker-deployment/      # Ansible-based deployment on bare Docker (active)
├── frontend/               # Streamlit management console (active)
├── scripts/                # Helper scripts: CLI wrapper, smoke tests, templates
├── k8-deployment/          # Kubernetes/Helm deployment (work in progress)
├── README-control-node     # Manual setup guide for the central hub node
└── README-worker-node      # Manual setup guide for worker nodes
```

---

## Architecture overview

```
  ┌─────────────────────────────────────────────────────┐
  │  Ansible Control Machine  (your laptop / CI runner) │
  │                                                     │
  │  docker-deployment/site.yml  ──────────────────┐   │
  │  scripts/brane_helper.sh (interactive menu)    │   │
  │  frontend/ (Streamlit GUI)                     │   │
  └────────────────────────────────────────────────┼───┘
                                                   │ SSH
          ┌────────────────────────────────────────┼──────────────┐
          │                                        ▼              │
          │  VM 1 – Central Hub                                   │
          │  ┌──────────────────────────────────────────────┐    │
          │  │  brane-api  brane-drv  brane-plr  ScyllaDB   │    │
          │  └──────────────────────────────────────────────┘    │
          │          ▲ mTLS (port 50051/50052)                    │
          │  VM 2 – Worker Node 1                                 │
          │  ┌─────────────────────────────┐                     │
          │  │  brane-worker  brane-chk    │                     │
          │  └─────────────────────────────┘                     │
          │  VM 3 – Worker Node 2                                 │
          │  ┌─────────────────────────────┐                     │
          │  │  brane-worker  brane-chk    │                     │
          │  └─────────────────────────────┘                     │
          └───────────────────────────────────────────────────────┘
```

---

## Quick start

### Prerequisites

- Ansible ≥ 2.14 on your control machine
- SSH key-based access to all target VMs
- Python 3.10+ (for the Streamlit frontend)
- Docker installed on all target VMs (handled by Ansible)

### Step 1 – Prepare the control node

Follow [README-control-node](README-control-node) to understand the expected directory layout on the central hub VM.

### Step 2 – Prepare worker nodes

Follow [README-worker-node](README-worker-node) for certificate and configuration steps on each worker VM.

### Step 3 – Configure the Ansible inventory

Edit `docker-deployment/inventories/production/hosts.ini`:

```ini
[central]
hub-vm-1 ansible_host=<CENTRAL_IP> central_ip=<CENTRAL_IP> location_id=central-hub

[workers]
worker-vm-2 ansible_host=<WORKER1_IP> node_ip=<WORKER1_IP> location_id=client-node-1 central_ip=<CENTRAL_IP>
worker-vm-3 ansible_host=<WORKER2_IP> node_ip=<WORKER2_IP> location_id=client-node-2 central_ip=<CENTRAL_IP>
```

Set `brane_user_home` in `docker-deployment/group_vars/all.yml` to match the remote user's home directory.

### Step 4 – Run the deployment

```bash
cd docker-deployment
pip install -r requirements.txt          # ansible + plugins

# Full deployment (all stages)
ansible-playbook -i inventories/production/hosts.ini site.yml

# Or step by step using tags:
ansible-playbook -i inventories/production/hosts.ini site.yml --tags prerequisites
ansible-playbook -i inventories/production/hosts.ini site.yml --tags branectl
ansible-playbook -i inventories/production/hosts.ini site.yml --tags workers
ansible-playbook -i inventories/production/hosts.ini site.yml --tags central
ansible-playbook -i inventories/production/hosts.ini site.yml --tags certs
ansible-playbook -i inventories/production/hosts.ini site.yml --tags start
ansible-playbook -i inventories/production/hosts.ini site.yml --tags smoke
```

### Step 5 – Optional: launch the Streamlit frontend

```bash
cd frontend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
streamlit run homepage.py
```

See [frontend/README.md](frontend/README.md) for configuration details.

### Step 6 – Optional: interactive helper script

```bash
# Configure once (copy and edit the example)
cp scripts/.brane_helper.env.example scripts/.brane_helper.env
$EDITOR scripts/.brane_helper.env

# Launch the interactive menu
bash scripts/brane_helper.sh
```

See [scripts/README.md](scripts/README.md) for details.

---

## Network ports

| Direction | Source            | Destination | Port  | Purpose                          |
|-----------|-------------------|-------------|-------|----------------------------------|
| Inbound   | Ansible ctrl node | All VMs     | 22    | SSH / Ansible                    |
| Inbound   | Admin / CI        | Central VM  | 50051 | Brane registry (package push)    |
| Inbound   | Worker VMs        | Central VM  | 50051 | Workers connecting to central    |
| Inbound   | Central + Workers | Worker VMs  | 50052 | Inter-worker data transfer/proxy |
| Outbound  | All VMs           | Internet    | 80/443| Docker image pulls, binary DL    |

---

## Security notes

- CA private key (`ca-key.pem`) is generated on the central hub and **purged** from worker nodes and the control machine immediately after certificate signing. See [docker-deployment/README.md](docker-deployment/README.md) for the full key lifecycle.
- **Never commit** private keys, `.pem` files, or host-specific `.env` files. They are covered by `.gitignore`.
- For production use, consider Ansible Vault for any secrets that must be versioned.

---

## Components

| Component           | Status        | Description                                  |
|---------------------|---------------|----------------------------------------------|
| `docker-deployment` |  Active      | Ansible roles for bare-Docker Brane cluster  |
| `frontend`          |  Active      | Streamlit GUI control plane                  |
| `scripts`           |  Active      | Helper scripts, smoke tests, templates       |
| `k8-deployment`     |  In progress | Kubernetes / Helm deployment (not yet ready) |

---

## Contributing

1. Fork the repo and create a feature branch.
2. Run linters locally before pushing:
   ```bash
   cd docker-deployment && bash test-lint.sh
   shellcheck scripts/*.sh
   ```
3. Open a pull request against `main`.

