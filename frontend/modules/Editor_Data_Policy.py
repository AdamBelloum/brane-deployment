import os
import subprocess
import threading
import queue
import time
import streamlit as st

# Setup paths matching your deployment structure
POLICY_DIR = os.path.abspath("./policies/")
os.makedirs(POLICY_DIR, exist_ok=True)

# Initialize cross-thread communication state tracking
if "policy_log_queue" not in st.session_state:
    st.session_state.policy_log_queue = queue.Queue()
if "global_policy_status" not in st.session_state:
    st.session_state.global_policy_status = "idle"
if "global_policy_logs" not in st.session_state:
    st.session_state.global_policy_logs = []


def async_policy_worker(cmd, log_queue):
    """Independent background thread managing policy subprocesses without blocking the UI."""
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        
        for line in iter(process.stdout.readline, ''):
            log_queue.put({"type": "log", "content": line})
            
        process.stdout.close()
        return_code = process.wait()
        
        if return_code == 0:
            log_queue.put({"type": "status", "content": "success"})
        else:
            log_queue.put({"type": "log", "content": f"\n❌ Process terminated with error code: {return_code}\n"})
            log_queue.put({"type": "status", "content": "failed"})
            
    except Exception as e:
        log_queue.put({"type": "log", "content": f"\n❌ Policy Engine Thread Exception: {str(e)}\n"})
        log_queue.put({"type": "status", "content": "failed"})


def render_data_policy():
    st.title("🔒 Institutional Data Access Policy Engine (eFLINT)")
    st.write("Declare data compliance governance, specify allowable analytical actions, and distribute rules to your worker nodes.")

    with st.expander("📖 Compliance Governance Guidelines", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("""
            **What it does:** Authors and activates formal eFLINT security expressions directly on worker nodes to control and enforce absolute data privacy restrictions.
            """)
        with col_b:
            st.markdown("""
            **Who is this for:** Data Protection Officers (DPOs) and Domain Infrastructure Admins.
            **Prerequisites:** A valid administrative token (`policy_token.json`) mapping secure handshake rights to target nodes.
            """)

    st.divider()

    st.subheader("🌐 Official Brane Policy Reasoner GUI")
    st.markdown(
        """
        You can use the official Brane Policy Reasoner workspace to graphically map complex rules:
        * **External Web App:** [Launch Brane Policy Reasoner GUI](https://github.com/braneframework/policy-reasoner-gui)
        """
    )

    st.divider()

    # Target worker nodes mapping configuration
    worker_nodes = {
        "Client Node 1 (worker-vm-2)": "http://145.100.135.172",
        "Client Node 2 (worker-vm-3)": "http://145.100.135.241"
    }

    # Initialize persistent workspace form selections
    if "cfg_policy_node" not in st.session_state:
        st.session_state.cfg_policy_node = list(worker_nodes.keys())[0]
    if "cfg_policy_token" not in st.session_state:
        st.session_state.cfg_policy_token = "./config/policy_token.json"
    if "cfg_policy_filename" not in st.session_state:
        st.session_state.cfg_policy_filename = "strict_privacy.eflint"
    if "cfg_policy_code" not in st.session_state:
        st.session_state.cfg_policy_code = """// Declare eFLINT Domain Constraints
fact Asset.
fact User.
fact Action.

relation allowed_to_run(User, Action, Asset).

// Security enforcement logic example
placeholder asset_rule {
    terminate if allowed_to_run(user, action, asset) == false;
}"""

    # -------------------------------------------------------------------
    # WORKSPACE DESIGN LAYOUT
    # -------------------------------------------------------------------
    col_setup, col_code = st.columns([2, 3])

    with col_setup:
        st.subheader("⚙️ Target Node Routing Parameters")
        selected_node_label = st.selectbox("Target Node Endpoint:", list(worker_nodes.keys()), key="policy_node_select")
        st.session_state.cfg_policy_node = selected_node_label
        target_node_url = worker_nodes[selected_node_label]
        
        token_path = st.text_input("Administrative Auth Token Path:", value=st.session_state.cfg_policy_token, key="policy_token_input")
        st.session_state.cfg_policy_token = token_path
        
        policy_filename = st.text_input("Governance Filename Output:", value=st.session_state.cfg_policy_filename, key="policy_filename_input")
        st.session_state.cfg_policy_filename = policy_filename

    with col_code:
        st.subheader("📝 eFLINT Policy Expression Pad")
        policy_code = st.text_area("Write compliance statements:", value=st.session_state.cfg_policy_code, height=220, key="policy_code_input")
        st.session_state.cfg_policy_code = policy_code

    st.divider()
    st.subheader("🛠️ Deployment Lifecycle Tasks")

    col_btn1, col_btn2 = st.columns(2)
    is_policy_running = st.session_state.global_policy_status == "running"

    with col_btn1:
        st.markdown("#### Pass 1: Submit Code to Node Registry")
        if st.button("1. Compile & Publish Policy File", type="primary", disabled=is_policy_running, key="policy_btn_submit"):
            # Write out local policy file asset
            target_policy_path = os.path.join(POLICY_DIR, policy_filename)
            with open(target_policy_path, "w") as f:
                f.write(policy_code)
                
            st.session_state.global_policy_logs = [f"💾 Saved eFLINT policy configuration locally to `{target_policy_path}`\n"]
            st.session_state.policy_log_queue = queue.Queue()
            
            # Formulate push command: branectl policy upload <PATH> --node http://<ADDR>
            cmd = ["branectl", "policy", "upload", target_policy_path, "--node", target_node_url]
            st.session_state.global_policy_logs.append(f"=== Spawning Registration Pipeline: {' '.join(cmd)} ===\n")
            
            st.session_state.global_policy_status = "running"
            t = threading.Thread(target=async_policy_worker, args=(cmd, st.session_state.policy_log_queue), daemon=True)
            t.start()
            st.rerun()

    with col_btn2:
        st.markdown("#### Pass 2: Activate Rule Set Across Node Mesh")
        policy_id_input = st.text_input("Enter Policy ID to activate:", value="", placeholder="e.g. 4a8b9c...", key="policy_id_activation_input")
        
        if st.button("2. Activate Policy ID", type="primary", disabled=is_policy_running or not policy_id_input, key="policy_btn_activate"):
            st.session_state.global_policy_logs = [f"⏳ Activating cluster rule layout signature: {policy_id_input}\n"]
            st.session_state.policy_log_queue = queue.Queue()
            
            # Build activation command: branectl policy activate <ID> --node http://<ADDR> --token ./token.json
            cmd = [
                "branectl", "policy", "activate", policy_id_input,
                "--node", target_node_url,
                "--token", token_path
            ]
            st.session_state.global_policy_logs.append(f"=== Spawning Activation Pipeline: {' '.join(cmd)} ===\n")
            
            st.session_state.global_policy_status = "running"
            t = threading.Thread(target=async_policy_worker, args=(cmd, st.session_state.policy_log_queue), daemon=True)
            t.start()
            st.rerun()

    # -------------------------------------------------------------------
    # LIVE STREAM LOG DISPLAY
    # -------------------------------------------------------------------
    st.markdown("### 🖥️ Compliance Engine Output Stream")
    
    if st.session_state.global_policy_status == "idle":
        st.info("Policy Engine idle. Submit or activate a policy statement above to view process output tracks.")
    elif st.session_state.global_policy_status == "running":
        st.warning("⚡ Processing policy request in the background. You can navigate away safely.")
    elif st.session_state.global_policy_status == "success":
        st.success("🎉 Transaction Completed Successfully! Review the tracking output details below.")
    elif st.session_state.global_policy_status == "failed":
        st.error("❌ Policy task aborted with errors. Inspect the transaction logs below.")

    terminal_area = st.empty()

    if st.session_state.global_policy_status == "running":
        while st.session_state.global_policy_status == "running":
            # Consume new logs safely on the main thread
            while not st.session_state.policy_log_queue.empty():
                item = st.session_state.policy_log_queue.get()
                if item["type"] == "status":
                    st.session_state.global_policy_status = item["content"]
                elif item["type"] == "log":
                    st.session_state.global_policy_logs.append(item["content"])
            
            terminal_area.code("".join(st.session_state.global_policy_logs), language="bash")
            time.sleep(0.4)
        st.rerun()
    else:
        logs = "".join(st.session_state.global_policy_logs)
        if logs:
            terminal_area.code(logs, language="bash")
