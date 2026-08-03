# Brane Cluster Management Console

A Streamlit-based GUI that lets a Brane administrator deploy, configure, and operate a Brane cluster without touching raw terminal commands.

The frontend is a companion to the Ansible automation in `docker-deployment/`. It does **not** replace the Ansible playbooks — it drives them and wraps the Brane CLI in an interactive web interface.

---

## Quick start

```bash
cd brane-deployment/frontend

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Launch
streamlit run homepage.py
```

The app opens at `http://localhost:8501` by default.

---

## Configuration

All paths are resolved automatically from the repo layout. You can override them with environment variables before launching:

| Variable            | Default                                          | Description                              |
|---------------------|--------------------------------------------------|------------------------------------------|
| `BRANE_ANSIBLE_DIR` | `<repo>/docker-deployment`                       | Path to the Ansible docker-deployment dir |
| `BRANE_INVENTORY`   | `<repo>/docker-deployment/inventories/production/hosts.ini` | Ansible inventory file |
| `BRANE_PLAYBOOK`    | `<repo>/docker-deployment/site.yml`              | Master Ansible playbook                  |
| `BRANE_CLI`         | auto-detected (`~/.local/bin/brane` → PATH)      | Path to the `brane` CLI binary           |

Example:

```bash
BRANE_ANSIBLE_DIR=/opt/brane/docker-deployment streamlit run homepage.py
```

---

## Pages

### Dashboard Home
Overview of the cluster status. Entry point when the app loads.

---

### Cluster Configurator
**File:** `modules/Cluster_Configurator.py`

Reads and writes `docker-deployment/inventories/production/hosts.ini` directly through the UI.

- View the current node topology (central hub + workers)
- Add or update a node (hostname alias, IP address, location ID)
- Remove a node
- Changes are written to `hosts.ini` immediately; run the Ansible playbook afterwards to apply them to the physical hosts

---

### Deploy Infrastructure
**File:** `modules/Deploy_Infrastructure.py`

Triggers the Ansible playbook (`site.yml`) asynchronously in the background.

- Select a deployment stage or run the full end-to-end sequence
- Monitors the running process and streams logs to the UI
- Shows status: idle → running → complete / failed
- You can navigate to other pages while a deployment is running; return and click **Refresh Logs** to see progress

Deployment stages available:
- Full deployment (all tags)
- Docker install
- Certificate exchange
- Start services

---

### Deploy Packages
**File:** `modules/Deploy_Packages.py`

Two tabs:

**Upload Custom Package** — compile and push a developer-provided Brane package to the central registry:
1. Upload a `container.yml` manifest
2. Upload a `.zip` of the source code
3. Provide a package name
4. The app builds and pushes it to the active central hub

**Run Smoke Test** — run a Hello World integration test to verify the cluster is working end-to-end:
- Choose Python or Bash runtime
- The app generates a minimal package, builds it, pushes it, runs a workflow, and shows the output

---

### Deploy Brane CLI
**File:** `modules/Deploy_cli.py`

Three tabs:

**Download & Install CLI** — detects your OS and architecture, downloads the correct `brane` binary from the nightly release, and installs it to `~/.local/bin/brane` without requiring root.

**User CLI Reference** — interactive quick-run buttons and a command reference table for data scientists and developers (`brane package`, `brane workflow`, `brane data`).

**Admin CLI Reference** — command reference for administrators (`branectl download`, `branectl generate`, `branectl start/stop`), with live start/stop buttons for cluster services.

---

### Editor — Brane Scripts
**File:** `modules/Editor_Brane_Scripts.py`

In-browser editor for writing and saving BraneScript (`.bs`) workflow files.

---

### Editor — Data Policy
**File:** `modules/Editor_Data_Policy.py`

In-browser editor for writing and saving Brane data policy files.

---

## File structure

```text
frontend/
├── homepage.py          # App entry point: page routing and global session state
├── requirements.txt     # Python dependencies
├── modules/
│   ├── config.py        # Centralised path and CLI configuration (import from here)
│   ├── home.py          # Dashboard Home page
│   ├── Cluster_Configurator.py
│   ├── Deploy_Infrastructure.py
│   ├── Deploy_Packages.py
│   ├── Deploy_cli.py
│   ├── Editor_Brane_Scripts.py
│   └── Editor_Data_Policy.py
└── README.md
```

---

## Prerequisites

- Python 3.10+
- The `brane` CLI binary installed locally (use the **Deploy Brane CLI** page to install it)
- Ansible installed and configured (for the **Deploy Infrastructure** page)
- SSH key-based access to the target VMs already set up
- `docker-deployment/inventories/production/hosts.ini` populated with your VM IPs (use the **Cluster Configurator** page)

