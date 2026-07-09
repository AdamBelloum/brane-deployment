import os
import subprocess
import threading
import queue
import time
import streamlit as st

# Setup Local Script Workspaces
SCRIPT_DIR = os.path.abspath("./workflow_codes/")
os.makedirs(SCRIPT_DIR, exist_ok=True)

# Initialize cross-thread communication primitives
if "script_log_queue" not in st.session_state:
    st.session_state.script_log_queue = queue.Queue()
if "global_script_status" not in st.session_state:
    st.session_state.global_script_status = "idle"
if "global_script_logs" not in st.session_state:
    st.session_state.global_script_logs = []


def async_script_worker(cmd, log_queue):
    """Independent background OS thread worker managing BraneScript executions."""
    try:
        process = subprocess.Popen(
            cmd, cwd=SCRIPT_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        
        for line in iter(process.stdout.readline, ''):
            log_queue.put({"type": "log", "content": line})
            
        process.stdout.close()
        return_code = process.wait()
        
        if return_code == 0:
            log_queue.put({"type": "status", "content": "success"})
        else:
            log_queue.put({"type": "log", "content": f"\n❌ Runtime terminated with error code: {return_code}\n"})
            log_queue.put({"type": "status", "content": "failed"})
            
    except Exception as e:
        log_queue.put({"type": "log", "content": f"\n❌ Engine Thread Exception: {str(e)}\n"})
        log_queue.put({"type": "status", "content": "failed"})


def render_brane_scripts():
    st.title("📜 BraneScript Workflow Studio")
    st.write("Compose parallelized pipelines, reference edge datasets securely, and execute workflows on the remote cluster mesh.")

    with st.expander("📖 Workflow Execution Guidelines", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("""
            **What it does:** Composes and schedules complex multi-party BraneScript analytics pipelines that safely execute computations without transferring raw data away from host environments.
            """)
        with col_b:
            st.markdown("""
            **Who is this for:** Data Scientists and Researchers.
            **Prerequisites:** Packages must already be compiled and published, and an active login tunnel to the Central Hub session must be initialized.
            """)

    st.divider()

    # -------------------------------------------------------------------
    # SEED PERSISTENT WORKSPACE STATE VALUES
    # -------------------------------------------------------------------
    if "cfg_script_name" not in st.session_state:
        st.session_state.cfg_script_name = "my_analysis.bs"
        
    if "cfg_workflow_code" not in st.session_state:
        st.session_state.cfg_workflow_code = """// Import compiled package modules
import hello_world;

// Reference target dataset on its native worker node (data never moves)
let patient_data := new Data { name := "patient_records" };

// Execute logic loops
let count := 42;
if count > 10 {
    let result := hello_world();
    println(result);
} else {
    println("Threshold constraint not met.");
}"""

    # Main UI layout splitting: Left for Code Editor, Right for Documentation and Snippets
    col_editor, col_docs = st.columns([3, 2])

    with col_editor:
        st.subheader("📝 Script Canvas")
        script_name = st.text_input("Workflow Filename:", value=st.session_state.cfg_script_name, placeholder="e.g. medical_pipeline.bs", key="script_name_input")
        st.session_state.cfg_script_name = script_name
        
        workflow_code = st.text_area(
            "Write BraneScript code logic here:",
            value=st.session_state.cfg_workflow_code,
            height=400,
            key="workflow_code_input"
        )
        st.session_state.cfg_workflow_code = workflow_code

    with col_docs:
        st.subheader("💡 Code Quick-Inject Sheets")
        
        snippet_type = st.selectbox(
            "Choose Code Blueprint Template:",
            ["Dataset Analysis Loop", "While Iterator Pattern", "Conditional Gate Block"],
            key="snippet_type_select"
        )
        
        if snippet_type == "Dataset Analysis Loop":
            st.code("""let target_set := new Data { name := "records" };\nlet summary := analyze(target_set);\nprintln(summary);""", language="python")
        elif snippet_type == "While Iterator Pattern":
            st.code("""let i := 0;\nwhile i < 5 {\n    println(i);\n    i := i + 1;\n}""", language="python")
        elif snippet_type == "Conditional Gate Block":
            st.code("""if count > 10 {\n    println("High priority");\n} else {\n    println("Standard process");\n}""", language="python")
            
        st.markdown("""
        #### 📊 Standard Type Cheat Sheet
        * `String` : `"hello"`
        * `Integer` : `42`
        * `Real` : `3.14`
        * `Boolean` : `true / false`
        * `Data` : `new Data { name := "x" }`
        """)

    st.divider()
    st.subheader("🚀 Compilation & Execution Runtime Platform")

    col_net1, col_net2, col_net3 = st.columns(3)
    with col_net1:
        exec_target = st.radio("Target Routing Space Environment:", ["Remote Instance Mode", "Local Sandboxed Mode"], horizontal=True, key="exec_target_radio")
    with col_net2:
        instance_ip = st.text_input("Central Hub Instance URL:", value="145.100.135.209", key="instance_ip_input")
    with col_net3:
        instance_port = st.text_input("Engine Port Configuration:", value="50053", key="instance_port_input")

    is_script_running = st.session_state.global_script_status == "running"

    if st.button("Launch Workflow Stream Execution", type="primary", disabled=is_script_running):
        # 1. Save code cleanly down onto disk system 
        target_file_path = os.path.join(SCRIPT_DIR, script_name)
        with open(target_file_path, "w") as f:
            f.write(workflow_code)
            
        # Clear logs and reset communication queue channel
        st.session_state.global_script_logs = [
            f"💾 Saved script locally to `{target_file_path}`\n"
        ]
        st.session_state.script_log_queue = queue.Queue()
        
        # 2. Formulate runtime flag options based on environment parameters
        if exec_target == "Remote Instance Mode":
            st.session_state.global_script_logs.append(f"Connecting to live Brane mesh framework engine at `http://{instance_ip}:{instance_port}`...\n")
            cmd = ["brane", "workflow", "run", "--remote", f"http://{instance_ip}:{instance_port}", script_name]
        else:
            st.session_state.global_script_logs.append("Spinning up local secure offline diagnostic sandbox container profile...\n")
            cmd = ["brane", "workflow", "run", script_name]
            
        st.session_state.global_script_logs.append(f"=== Launching Engine Execution Pipe: {' '.join(cmd)} ===\n")
        
        # 3. Fire the background pipeline worker
        st.session_state.global_script_status = "running"
        t = threading.Thread(
            target=async_script_worker, 
            args=(cmd, st.session_state.script_log_queue), 
            daemon=True
        )
        t.start()
        st.rerun()

    # -------------------------------------------------------------------
    # LIVE STREAM LOG CONSUMER VIEW
    # -------------------------------------------------------------------
    st.markdown("### 🖥️ Workflow Execution Output Stream")
    
    if st.session_state.global_script_status == "idle":
        st.info("Workflow execution engine idle. Press launch above to trigger pipeline verification.")
    elif st.session_state.global_script_status == "running":
        st.warning("⚡ Workflow execution currently processing across microservices infrastructure...")
    elif st.session_state.global_script_status == "success":
        st.success("🎉 Workflow Execution Pipeline Completed Successfully!")
    elif st.session_state.global_script_status == "failed":
        st.error("❌ Execution terminated due to runtime errors. Check engine context trace log rules below.")

    terminal_area = st.empty()

    if st.session_state.global_script_status == "running":
        while st.session_state.global_script_status == "running":
            # Safely drain updates off the background queue on the main UI thread
            while not st.session_state.script_log_queue.empty():
                item = st.session_state.script_log_queue.get()
                if item["type"] == "status":
                    st.session_state.global_script_status = item["content"]
                elif item["type"] == "log":
                    st.session_state.global_script_logs.append(item["content"])
            
            terminal_area.code("".join(st.session_state.global_script_logs), language="bash")
            time.sleep(0.4)
        st.rerun()
    else:
        logs = "".join(st.session_state.global_script_logs)
        if logs:
            terminal_area.code(logs, language="bash")
