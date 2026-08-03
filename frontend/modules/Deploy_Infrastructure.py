import os
import subprocess
import streamlit as st

# ===================================================================
# BULLETPROOF PATH ROUTING FOR THE MODULAR LAYOUT
# ===================================================================
#CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
#ANSIBLE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../docker-deployment"))
#INVENTORY = os.path.join(ANSIBLE_DIR, 'inventories/production/hosts.ini')
from config import ANSIBLE_DIR, INVENTORY_PATH as INVENTORY


def render_infra_deploy():
    st.title(" Infrastructure Orchestration Engine")
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

    # Ensure the background process handle structure exists in session state
    if "global_infra_proc" not in st.session_state:
        st.session_state.global_infra_proc = None

    # ===================================================================
    #  LIVE BACKGROUND MONITORING ENGINE
    # ===================================================================
    # If a process is actively running, drain its output buffer without blocking the page
    if st.session_state.global_infra_status == "running" and st.session_state.global_infra_proc is not None:
        proc = st.session_state.global_infra_proc
        
        # Check if the process has finished on its own
        return_code = proc.poll()
        
        # Make stdout non-blocking so we can read whatever text is currently waiting
        try:
            os.set_blocking(proc.stdout.fileno(), False)
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                # Append to your global log list initialized in homepage.py
                st.session_state.global_infra_logs.append(line)
        except Exception:
            pass

        if return_code is not None:
            # The process completed while we were monitoring or away!
            if return_code == 0:
                st.session_state.global_infra_status = "complete"
            else:
                st.session_state.global_infra_status = "failed"
            st.session_state.global_infra_proc = None
            st.rerun()

    # ===================================================================
    #  RENDERING STATES
    # ===================================================================
    
    # STATE 1: IDLE (Ready to run)
    if st.session_state.global_infra_status == "idle":
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
            
            # Start the execution completely asynchronously using Popen
            process = subprocess.Popen(
                cmd, cwd=ANSIBLE_DIR,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                bufsize=1
            )
            
            # Update session state properties immediately
            st.session_state.global_infra_proc = process
            st.session_state.global_infra_status = "running"
            st.session_state.global_infra_logs = ["🛫 Spawning background execution thread...\n"]
            st.rerun()

    # STATE 2: ACTIVE DEPLOYMENT
    elif st.session_state.global_infra_status == "running":
        st.warning("Infrastructure deployment execution loop is actively running in the background!")
        
        col_mon1, col_mon2 = st.columns([1, 4])
        with col_mon1:
            if st.button("Refresh Logs", type="primary"):
                st.rerun()
        with col_mon2:
            st.caption("You can safely switch to other pages. Click 'Refresh Logs' to see the latest streaming output.")

    # STATE 3: COMPLETED SUCCESSFULLY
    elif st.session_state.global_infra_status == "complete":
        st.success("Ansible Run Sequence Terminated Successfully!")
        st.info("""
        ### Next Step: Run System Verification Tests
        Your distributed cluster nodes are now fully configured, securely certified, and interconnected! 
        
        To verify that the microservice grid can compile and execute workloads across your new worker matrix:
        1. Navigate to **Deploy Packages** using the left sidebar menu.
        2. Run the automated **Hello World Cluster Smoke Test** to compile, register, and run your first distributed container payload!
        """)
        if st.button("Clear Deployment Session & Reset"):
            st.session_state.global_infra_status = "idle"
            st.session_state.global_infra_logs = []
            st.rerun()

    # STATE 4: FAILED EXECUTION
    elif st.session_state.global_infra_status == "failed":
        st.error(" Ansible deployment encountered an error state.")
        if st.button("Clear Deployment Session & Retry"):
            st.session_state.global_infra_status = "idle"
            st.session_state.global_infra_logs = []
            st.rerun()

    # ===================================================================
    # CONSOLE LOG DISPLAY WINDOW
    # ===================================================================
    if st.session_state.global_infra_logs:
        st.subheader(" Live Execution Log Trace")
        # Join the log list into a single string for st.code block formatting
        log_text = "".join(st.session_state.global_infra_logs)
        st.code(log_text, language="bash")
