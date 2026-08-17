# k8-deployment

> **Work in progress — not ready for use.**

This directory is a placeholder for the Kubernetes-based deployment of a Brane cluster.
The content here is an early draft and has not been tested or validated.

The active deployment method is [`docker-deployment/`](../docker-deployment/), which uses
Ansible on bare Docker and is fully operational.

---

## Planned approach

The k8s deployment will follow the same architecture as the Docker deployment but run on
a Kubernetes cluster (K3s) with Helm charts managing the Brane services.

Planned components:
- `brane-chart/` — Helm chart for central hub and worker nodes
- `roles/` — Ansible roles for K3s provisioning and secret management
- `deploy.yml` — master playbook

This will be developed once the Docker deployment is stable and the Kubernetes target
infrastructure is defined.

