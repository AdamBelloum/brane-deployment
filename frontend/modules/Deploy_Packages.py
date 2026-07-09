import os
import subprocess
import configparser
import zipfile
import shutil
import streamlit as st

# ===================================================================
# BULLETPROOF ABSOLUTE PATH RESOLUTION
# ===================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) 
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../..")) 
INVENTORY_PATH = os.path.join(REPO_ROOT, "docker-deployment/inventories/production/hosts.ini")

def get_central_ip():
    config = configparser.ConfigParser(allow_no_value=True, delimiters=(' ', '='))
    config.optionxform = str
    
    if os.path.exists(INVENTORY_PATH):
        config.read(INVENTORY_PATH)
        
        for section in config.sections():
            if "central" in section.lower():
                items = config.items(section)
                if items:
                    for key, val in items:
                        line_content = f"{key} {val if val else ''}"
                        for part in line_content.replace('=', ' ').split():
                            if part.replace('.', '').isdigit() and part.count('.') == 3:
                                return part
    return None

def render_packages_deploy():
    st.title("📦 Brane Package Deployment & Integration Testing")
    st.markdown("Use this panel to verify your cluster functionality by compiling, registering, and running a test execution payload.")

    central_ip = get_central_ip()
    if not central_ip:
        st.warning("⚠️ No central hub IP detected in your Cluster Configurator. Please set up your topology layout first.")
    else:
        st.info(f"🔗 Connected to Active Central Hub target IP: `{central_ip}`")

    st.divider()

    st.subheader("🚀 Deploy Operational Packages")
    tab1, tab2 = st.tabs(["📁 Upload Custom Admin Package", "🧪 Run Automated System Smoke Test"])

    # ===================================================================
    # TAB 1: CUSTOM USER PACKAGE UPLOADER (Matches original script layout)
    # ===================================================================
    with tab1:
        st.markdown("Use this tab to compile and register your custom functional Brane application containers.")
        
        col_u1, col_u2 = st.columns(2)
        with col_u1:
            uploaded_manifest = st.file_uploader("Upload your Package Manifest (`container.yml`):", type=["yml", "yaml"])
        with col_u2:
            uploaded_source = st.file_uploader("Upload Source Files Code Bundle (`.zip` format):", type=["zip"])

        custom_package_name = st.text_input("Confirm Package Target Name:", placeholder="e.g. image_processor")

        if st.button("Compile and Push Custom Package", type="primary", disabled=(central_ip is None)):
            if not uploaded_manifest or not uploaded_source or not custom_package_name:
                st.error("Please supply a manifest file, source zip archive, and target confirmation name to trigger the pipeline.")
            else:
                with st.status("🏗️ Building and Registering Custom Package...", expanded=True) as status:
                    user_dir = f"/tmp/brane-user-package-{custom_package_name}"
                    if os.path.exists(user_dir):
                        shutil.rmtree(user_dir)
                    os.makedirs(user_dir, exist_ok=True)
                    
                    st.write("📥 Staging raw source code elements onto file system...")
                    with open(os.path.join(user_dir, "container.yml"), "wb") as f:
                        f.write(uploaded_manifest.getbuffer())
                    
                    zip_path = os.path.join(user_dir, "source.zip")
                    with open(zip_path, "wb") as f:
                        f.write(uploaded_source.getbuffer())
                    
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(user_dir)
                        
                    for root, dirs, files in os.walk(user_dir):
                        for file in files:
                            os.chmod(os.path.join(root, file), 0o755)

                    st.write("🏗️ Calling backend Brane compiler tools...")
                    build_res = subprocess.run(["brane", "package", "build", "./container.yml"], cwd=user_dir, capture_output=True, text=True)
                    
                    if build_res.returncode != 0:
                        st.error(f"Compilation Failed:\n{build_res.stderr}")
                        status.update(label="Custom Package Compilation Failed", state="error")
                        st.stop()

                    st.write(f"🔑 Verifying session authority against hub context (http://{central_ip})...")
                    subprocess.run(["brane", "login", f"http://{central_ip}", "--username", "dashboard_user"], capture_output=True, text=True)
                    
                    st.write(f"🚀 Injecting compiled container bundle `{custom_package_name}` into central node registry...")
                    push_res = subprocess.run(["brane", "package", "push", custom_package_name], cwd=user_dir, capture_output=True, text=True)
                    
                    if push_res.returncode == 0:
                        status.update(label=f"✅ Package `{custom_package_name}` Registered Successfully!", state="complete")
                        st.success(f"🎉 Your custom package is live! Other engineers can now call 'import {custom_package_name};' inside their workflows.")
                    else:
                        status.update(label="❌ Registry Rejected Package Assets", state="error")
                        st.error(f"Registry output error trace:\n{push_res.stderr}")

    # ===================================================================
    # TAB 2: AUTOMATED INTEGRATION TEST WORKSPACE (Your Exact Hello World Fix)
    # ===================================================================
    with tab2:
        st.markdown("Use this tab to run the baseline system integration verification smoke test.")
        test_mode = st.selectbox("Select Test Framework Engine:", ["Python-based Package (Recommended)", "Bash Shell-based Package"])
        
        if st.button("Run Hello World Integration Test", type="primary", disabled=(central_ip is None)):
            with st.status("🚀 Initializing Integration Smoke Test...", expanded=True) as status:
                test_dir = "/tmp/hello-world-test"
                if os.path.exists(test_dir):
                    shutil.rmtree(test_dir)
                os.makedirs(test_dir, exist_ok=True)
                
                container_yml_path = os.path.join(test_dir, "container.yml")
                
                if "Python" in test_mode:
                    st.write("📝 Designing automated test script scripts for Python Runtime...")
                    script_path = os.path.join(test_dir, "analyze.py")
                    with open(script_path, "w") as f:
                        f.write('#!/usr/bin/env python3\nimport yaml\nprint(yaml.dump({"output": "Hello from Python Distributed Container!"}, default_flow_style=True).strip())\n')
                    os.chmod(script_path, 0o755)
                    
                    with open(container_yml_path, "w") as f:
                        f.write("name: python_hello\nversion: 1.0.0\nkind: ecu\ndependencies:\n  - python3\n  - python3-yaml\nfiles:\n  - analyze.py\nentrypoint:\n  kind: task\n  exec: analyze.py\nactions:\n  'hello':\n    command:\n    input:\n    output:\n    - name: output\n      type: string\n")
                    package_name = "python_hello"
                else:
                    st.write("📝 Designing automated test script manifests for Bash Environment...")
                    script_path = os.path.join(test_dir, "hello_world.sh")
                    with open(script_path, "w") as f:
                        f.write('#!/bin/bash\necho \'output: "Hello from Bash Distributed Container!"\'\n')
                    os.chmod(script_path, 0o755)
                    
                    with open(container_yml_path, "w") as f:
                        f.write("name: bash_hello\nversion: 1.0.0\nkind: ecu\nfiles:\n  - hello_world.sh\nentrypoint:\n  kind: task\n  exec: hello_world.sh\nactions:\n  'hello_world':\n    command:\n    input:\n    output:\n    - name: output\n      type: string\n")
                    package_name = "bash_hello"

                st.write("🏗️ Compiling test application container assets via Brane local builder...")
                build_res = subprocess.run(["brane", "package", "build", "./container.yml"], cwd=test_dir, capture_output=True, text=True)
                
                if build_res.returncode != 0:
                    st.error(f"Compilation Failed:\n{build_res.stderr}")
                    status.update(label="Test Pipeline Errored", state="error")
                    st.stop()

                st.write("🔑 Synchronizing authentication profile with Central Hub...")
                subprocess.run(["brane", "login", f"http://{central_ip}", "--username", "admin_tester"], capture_output=True, text=True)
                
                st.write(f"📤 Transferring test binary footprint `{package_name}` to registry...")
                subprocess.run(["brane", "package", "push", package_name], cwd=test_dir, capture_output=True, text=True)

                workflow_file = os.path.join(test_dir, "workflow.bs")
                with open(workflow_file, "w") as f:
                    if "Python" in test_mode:
                        f.write("import python_hello;\nprint(python_hello.hello());\n")
                    else:
                        f.write("import bash_hello;\nprint(bash_hello.hello_world());\n")

                st.write("📝 Scheduling workflow test script assembly to active orchestration engine...")
                run_res = subprocess.run(
                    ["brane", "workflow", "run", "workflow.bs", "--remote", f"http://{central_ip}:50053"], 
                    cwd=test_dir, capture_output=True, text=True
                )

                if run_res.returncode == 0:
                    status.update(label="✅ Integration Test Completed Successfully!", state="complete")
                    st.subheader("🎉 Execution Output Verification Stream")
                    st.code(run_res.stdout, language="yaml")
                else:
                    status.update(label="❌ Pipeline Execution Interrupted", state="error")
                    st.error(f"Workflow execution engine encountered an error state:\n{run_res.stderr}")
