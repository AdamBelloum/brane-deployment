---

## Repository Structure

```text
brane-docker-deployment/
├── inventories/
│   └── production/
│       └── hosts.ini            # Infrastructure IPs and location mappings
├── roles/
│   ├── docker_setup/            # Installs Docker, system packages, and branectl
│   │   └── tasks/
│   │       └── main.yml
│   ├── brane_central/           # Prepares, keys, and boots the Central Hub (VM 1)
│   │   └── tasks/
│   │       └── main.yml
│   └── brane_workers/           # Attaches and spins up Worker Nodes (VM 2 & 3)
│       └── tasks/
│           └── main.yml
├── group_vars/
│   └── all.yml                  # Global variable overrides (URLs, users)
└── brane_package_deployer/   <-- NEW ROLE
        ├── files/               
        │   ├── package_A/       # Place developer code & container.yml here
        │   └── package_B/       
        └── tasks/
            └── main.yml         # Automation tasks loop
└── deploy_docker.yml            # Master automated playbook orchestrator
```

# network configuration

Direction | Source | Destination| Port | ProtocolPurpose
Inbound | Ansible Control Node | All VMs (1, 2, 3) | 22                     | TCP Ansible Playbook Execution
Inbound | Admin Laptop         | CI/CD  VM1        | (XXX.XXX.XXX.XXX)30051 | TCP Brane CLI Package Pushing
Inbound | VM2 & VM3            | VM1               | (XXX.XXX.XXX.XXX)50051 | TCPWorkers connecting to Central Hub
Inbound | VM1 & Cross-Workers  | VM2 & VM          | 350052                 | TCPInter-worker data transfer & proxy
Outbound| All VMs              | Internet          | 80, 443                | TCP

# Cryptographic Key Management & Security Matrix

To prevent manual manipulation and security risks, this automation utilizes an ephemeral trust orchestration loop:

- CA Initialization: The Root CA certificate (ca.pem) and private key (ca-key.pem) are generated strictly within the isolated environment of the Central Hub.

- Secure Transport: The playbook securely draws the CA keypair back to a protected path (/tmp/brane_certs) on the local Ansible Control machine via encrypted SSH tunnels.

Just-In-Time Node Signing: The CA assets are deployed to the Worker hosts to locally generate unique, cryptographically signed node keypairs mapped explicitly to their private hostnames.

- Permanent Purging: The playbook systematically deletes the master ca-key.pem from the Worker nodes and the local Control machine instantly post-generation, eliminating data residue vectors.

- Key Placement Topology
  - Cryptographic Asset	Central Hub VM	Worker Node VMs	Description	Risk Scoping
  - ca.pem	Key Present	Key Present	Public root authority verifier.	Public Domain / Low
  - ca-key.pem	Key Present	Purged	Cluster master signing identity.	Critical / Confined
  - worker-key.pem	Absent	Key Present	Node-specific target mTLS secret.	High / Bound to VM

# Deployment Configuration Prerequisites

## 1. Update the Host Layout

Open inventories/production/hosts.ini and modify the IP mappings to point precisely to your active target cloud or infrastructure interfaces:

```YML
Ini, TOML
[central_hub]
hub-vm-1 ansible_host=192.168.1.10 central_ip=192.168.1.10 location_id=central-hub

[worker_nodes]
worker-vm-2 ansible_host=192.168.1.11 node_ip=192.168.1.11 location_id=client-node-1 central_ip=192.168.1.10
worker-vm-3 ansible_host=192.168.1.12 node_ip=192.168.1.12 location_id=client-node-2 central_ip=192.168.1.10

```

## 2. Verify Global Variables
Ensure the remote system deployment user and version tags line up with your base images in group_vars/all.yml:

```YAML
---
ansible_user: ubuntu
branectl_url: "[https://github.com/braneframework/brane/releases/latest/download/branectl-linux-x86_64](https://github.com/braneframework/brane/releases/latest/download/branectl-linux-x86_64)"
```

## Execution Guide

- Provision and Bootstrap Cluster
- Run the master playbook from the repository root directory. Ensure that you have configure SSH public key authentication to the target VMs.

```Bash
ansible -i inventories/production/hosts.ini deploy_docker.yml
```

## Concrete Example of What to Collect
If a developer writes a Python function to clean data, they must hand over a folder structured exactly like this:

```Plaintext
package_name/                <-- The package directory
├── brane-function-code.py    <-- The source code asset
└── container.yml             <-- The mandatory interface blueprint
```


## Manual Infrastructure Verification
To verify the deployment success directly on any node, SSH into the target host and inspect the container topologies:

```Bash
# Verify all baseline components are active
docker ps

# Check the local proxy interface routing status
docker logs brane-proxy

# View live system diagnostic logs on the central engine
cd ~/brane-central && branectl logs
```
## Maintenance and Cluster Lifecycle Operations
Because this deployment runs on bare Docker without Kubernetes orchestration, scaling and image lifecycle management must be driven directly via Ansible:

## Stopping the Cluster Ecosystem

```Bash
# Execute localized container termination on individual node structures
branectl stop central  # On VM 1
branectl stop worker   # On VM 2 & VM 3
Upgrading the Cluster Images
```

To update or refresh Brane container software layers, pull down new images and execute a sequential orchestrator reboot:

```Bash
# Download and re-init updates via terminal execution
branectl download central && branectl start central


with open("README.md", "w") as f:
f.write(readme_content)
print("File written successfully.")

Your production-grade markdown `README.md` file for the bare Docker-based Brane cluster deployment is ready. 

[file-tag: code-generated-file-0-1781703253798889989]

### What this README contains:
1. **Architectural Overview:** A visual text-diagram showing the layout of the Ansible Control Node mapping down to the separate VM topologies.
2. **Project Tree:** Clear representation of the roles, inventory directories, and configurations provided in the project structure.
3. **Security Matrix:** A detailed guide on how the cluster's Certificate Authority (`ca-key.pem`) is handled, moved via encrypted SSH, and strictly purged from host systems to avoid multi-tenant vulnerabilities.
4. **Step-by-Step Execution Guide:** Concrete commands on how to run the automated playbook, map the hosts file correctly, and inspect container daemon runtime flags once live.
