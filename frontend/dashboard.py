import os
import subprocess
import streamlit as st

# Configure the directory where your playbooks live
ANSIBLE_DIR = os.path.abspath("../brane-depoyment/docker-deployment/")
INVENTORY = os.path.join(ANSIBLE_DIR, 'inventories/production/hosts.ini')

st.set_page_config(page_title="Brane Deployment Center", page_icon="🚀", layout="wide")

st.title("🚀 Brane Framework - Orchestration Dashboard")
st.write("Select a deployment phase below to sync and provision your cluster nodes.")

# 1. Create a simple sidebar or selection dropdown for phases
phase = st.radio(
    "Select Action:",
    [
        "Pass 0: Sync Docker Engine (docker_install)",
        "Pass 1: Generate Configurations",
        "Pass 2: Distribute & Exchange",
        "Pass 3: Start Services"
    ]
)

# Extract the tag based on choice
tag_map = {
    "Pass 0: Sync Docker Engine (docker_install)": "docker_install",
    "Pass 1: Generate Configurations": "generate_configs",
    "Pass 2: Distribute & Exchange": "distribute",
    "Pass 3: Start Services": "start_services"
}
selected_tag = tag_map[phase]

# 2. Trigger Button
if st.button("Execute Phase", type="primary"):
    st.info(f"Running playbook with tag: {selected_tag}... Please watch live logs below.")
    
    cmd = ['ansible-playbook', '-i', INVENTORY, 'deploy-brane.yml', '--tags', selected_tag]
    
    # Live stream console logs straight to the browser UI container
    log_area = st.empty()
    full_log = ""
    
    process = subprocess.Popen(
        cmd, cwd=ANSIBLE_DIR,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    
    for line in iter(process.stdout.readline, ''):
        full_log += line
        # Display logs in a nice code terminal block inside the browser
        log_area.code(full_log, language="bash")
        
    process.stdout.close()
    st.success("Execution Completed!")
