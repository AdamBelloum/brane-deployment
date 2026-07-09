import os
import subprocess
import streamlit as st

# ===================================================================
# BULLETPROOF PATH ROUTING FOR THE MODULAR LAYOUT
# ===================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Moves out of 'modules' and down into 'docker-deployment'
ANSIBLE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../docker-deployment"))
INVENTORY = os.path.join(ANSIBLE_DIR, 'inventories/production/hosts.ini')


def render_infra_deploy():
    st.title("🚀 Infrastructure Orchestration Engine")
    st.write("Trigger sequenced playbook updates across your compute nodes asynchronously.")

    with st.expander("📖 Operation Guidelines", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("""
            **What it does:** Executes sequenced Ansible automation plays across target servers to cleanly provision internal runtime environments, certificates, and cluster networks.
            """)
        with col_b:
            st.markdown("""
            **Who is this for:** System Administrators / DevOps Engineers.
            **Prerequisites:** Target node layouts must be applied inside the **Cluster Configurator** prior to running this deployment.
            """)

    st.divider()

    # Updated target mapping to match our new decoupled playbook structure
    phase = st.selectbox(
        "Select Target Deployment Action:",
        [
            "Full Automated End-to-End Deployment (Recommended)",
            "Pass 0: Uniform Container Engine Sync (docker_install)",
            "Pass 2: Distribute Local Asset Keys (exchange_certs)",
            "Pass 3: Launch Active Brane Cluster Services (start_services)"
        ]
    )

    tag_map = {
        "Full Automated End-to-End Deployment (Recommended)": "all",
        "Pass 0: Uniform Container Engine Sync (docker_install)": "docker_install",
        "Pass 2: Distribute Local Asset Keys (exchange_certs)": "exchange_certs",
        "Pass 3: Launch Active Brane Cluster Services (start_services)": "start_services"
    }

    selected_tag = tag_map[phase]

    if st.button("Launch Ansible Playbook Sequence", type="primary"):
        if selected_tag == "all":
            cmd = ['ansible-playbook', '-i', INVENTORY, 'deploy-brane.yml']
        else:
            cmd = ['ansible-playbook', '-i', INVENTORY, 'deploy-brane.yml', '--tags', selected_tag]
        
        # Live execution stream block
        log_area = st.empty()
        full_log = ""  
        
        process = subprocess.Popen(
            cmd, cwd=ANSIBLE_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        
        for line in iter(process.stdout.readline, ''):
            full_log += line
            log_area.code(full_log, language="bash")
            
        process.stdout.close()
        return_code = process.wait()
        
        if return_code == 0:
            st.success("🎉 Ansible Run Sequence Terminated Successfully!")
            
            # Restored original bright actionable guidance box 🚀
            st.info("""
            ### 🏁 Next Step: Run System Verification Tests
            
            Your distributed cluster nodes are now fully configured, securely certified, and interconnected! 
            
            To verify that the microservice grid can compile and execute workloads across your new worker matrix:
            1. Navigate to **📦 Deploy Packages** using the left sidebar menu.
            2. Run the automated **Hello World Cluster Smoke Test** to compile, register, and run your first distributed container payload!
            """)
        else:
            st.error(f"Ansible run encountered an error. Exit Code: {return_code}")
