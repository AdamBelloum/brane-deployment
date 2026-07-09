# 🌐 Brane Cluster Management Console

Welcome to the centralized orchestration room for the Brane Distributed Computing Framework. This Streamlit application serves as an interactive GUI control plane to configure infrastructure topologies, manage cryptographic keys locally, distribute security rules, and execute cross-site data analytics pipelines without touching raw terminal configurations.

---

## 🚀 Quick Start User Journey (Zero-Interaction Deployment)

To deploy or manage your Brane cluster infrastructure, follow this complete sequential workflow:

### 1. Host Workstation Setup
Initialize a clean, localized Python virtual environment on your control node/frontend workstation:

```bash
# Navigate to the frontend directory
cd brane-deployment/frontend

# Initialize and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install all locked core dependencies
pip install -r requirements.txt

# Launch the interactive web panel
streamlit run homepage.py
