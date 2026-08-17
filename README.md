# brane-deployment

Tooling to deploy and operate a [Brane](https://github.com/BraneFramework/brane) distributed computing cluster.

Brane is a programmable orchestration framework for distributed data pipelines across federated sites. This repository covers the full lifecycle: infrastructure provisioning, certificate exchange, service startup, package deployment, and policy management.

---

## Repository layout

```
brane-deployment/
├── docker-deployment/      # Ansible-based deployment on bare Docker (active)
├── k8s-deployment/         # Kubernetes/Helm deployment (work in progress)
├── frontend/               # Streamlit management console
├── scripts/                # Interactive helper suite (entry point: brane_main.sh)
├── packages/               # Brane packages (built locally, ignored by git)
├── datasets/               # Datasets used by workflows (ignored by git)
├── policies/               # eFLINT policy files
├── certs/                  # Domain certificates (ignored by git)
├── policy_tokens/          # Policy expert JWT tokens (ignored by git)
└── .gitignore
```

---

## Quick start

### Prerequisites

- Ansible ≥ 2.14 on your control machine
- SSH key-based access to all target VMs
- Python 3.10+ (for the Streamlit frontend)
- Docker installed on all target VMs (handled by Ansible)

### Step 1 — Clone and configure the inventory

```bash
git clone https://github.com/AdamBelloum/brane-deployment.git
cd brane-deployment
```

Edit `docker-deployment/inventories/production/hosts.ini`:

```ini
[central]
hub-vm-1 ansible_host=<CENTRAL_IP> central_ip=<CENTRAL_IP> location_id=central-hub

[workers]
worker-vm-2 ansible_host=<WORKER1_IP> node_ip=<WORKER1_IP> location_id=client-node-1 central_ip=<CENTRAL_IP>
worker-vm-3 ansible_host=<WORKER2_IP> node_ip=<WORKER2_IP> location_id=client-node-2 central_ip=<CENTRAL_IP>
```

Set `brane_user_home` in `docker-deployment/group_vars/all.yml` to match the remote user's home directory.

### Step 2 — Launch the helper

```bash
bash scripts/brane_main.sh
```

The helper reads `hosts.ini` automatically and presents a role-based menu:

- **User** — manage packages, certificates, and run workflows
- **Admin** — deploy and manage the Brane infrastructure via Ansible
- **Policy Manager** — add and activate eFLINT domain policies

### Step 3 — Or run Ansible directly

```bash
cd docker-deployment
pip install -r requirements.txt

# Full deployment
ansible-playbook -i inventories/production/hosts.ini site.yml

# Step by step
ansible-playbook -i inventories/production/hosts.ini site.yml --tags prerequisites
ansible-playbook -i inventories/production/hosts.ini site.yml --tags branectl
ansible-playbook -i inventories/production/hosts.ini site.yml --tags workers
ansible-playbook -i inventories/production/hosts.ini site.yml --tags central
ansible-playbook -i inventories/production/hosts.ini site.yml --tags certs
ansible-playbook -i inventories/production/hosts.ini site.yml --tags start
ansible-playbook -i inventories/production/hosts.ini site.yml --tags smoke
```

### Step 4 — Optional: Streamlit frontend

```bash
cd frontend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
streamlit run homepage.py
```

See [frontend/README.md](frontend/README.md) for configuration details.

---

## Architecture

```
  ┌──────────────────────────────────────────────────────┐
  │  Control Machine  (your laptop)                      │
  │                                                      │
  │  scripts/brane_main.sh  (interactive helper)    ─┐  │
  │  docker-deployment/site.yml  (Ansible)           │  │
  │  frontend/  (Streamlit GUI)                      │  │
  └──────────────────────────────────────────────────┼──┘
                                                     │ SSH
        ┌────────────────────────────────────────────┼────────────┐
        │                                            ▼            │
        │  VM 1 – Central Hub                                     │
        │  ┌────────────────────────────────────────────────┐    │
        │  │  brane-api  brane-drv  brane-plr  ScyllaDB     │    │
        │  └────────────────────────────────────────────────┘    │
        │          ▲ mTLS (port 50051/50052)                      │
        │  VM 2 – Worker Node 1                                   │
        │  ┌──────────────────────────────┐                      │
        │  │  brane-job  brane-chk        │                      │
        │  └──────────────────────────────┘                      │
        │  VM 3 – Worker Node 2                                   │
        │  ┌──────────────────────────────┐                      │
        │  │  brane-job  brane-chk        │                      │
        │  └──────────────────────────────┘                      │
        └─────────────────────────────────────────────────────────┘
```

---

## Network ports

| Direction | Source | Destination | Port | Purpose |
|---|---|---|---|---|
| Inbound | Control machine | All VMs | 22 | SSH / Ansible |
| Inbound | Admin / CI | Central VM | 50051 | Brane registry |
| Inbound | Worker VMs | Central VM | 50051 | Workers → central |
| Inbound | Central + Workers | Worker VMs | 50052 | Inter-worker transfer |
| Outbound | All VMs | Internet | 80/443 | Docker image pulls |

---

## Components

| Component | Status | Description |
|---|---|---|
| `docker-deployment` | Active | Ansible deployment on bare Docker |
| `frontend` | Active | Streamlit GUI control plane |
| `scripts` | Active | Role-based interactive helper suite |
| `k8s-deployment` | Work in progress | Kubernetes / Helm deployment |

---

## Security notes

- CA private key (`ca-key.pem`) is generated on the central hub and purged immediately after certificate signing.
- **Never commit** private keys, `.pem` files, or `.env` files — covered by `.gitignore`.
- `certs/` and `policy_tokens/` are local-only and git-ignored.

