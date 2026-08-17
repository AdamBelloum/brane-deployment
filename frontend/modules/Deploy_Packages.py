import os
import subprocess
import zipfile
import shutil
import streamlit as st

from modules.config import INVENTORY_PATH, get_brane_executable, get_central_ip


def render_packages_deploy():
    st.title("Brane Package Deployment & Integration Testing")
    st.markdown(
        "Use this panel to verify your cluster functionality by compiling, "
        "registering, and running a test execution payload."
    )

    central_ip = get_central_ip()
    if not central_ip:
        st.warning(
            "No central hub IP detected. "
            "Configure your inventory in the **Cluster Configurator** first."
        )
    else:
        st.info(f"Connected to central hub: `{central_ip}`")

    st.divider()
    st.subheader("Deploy Operational Packages")

    tab1, tab2 = st.tabs(["Upload Custom Package", "Run Smoke Test"])

    # =========================================================================
    # TAB 1: CUSTOM USER PACKAGE UPLOADER
    # =========================================================================
    with tab1:
        st.markdown(
            "Compile and register your custom Brane application container."
        )

        col_u1, col_u2 = st.columns(2)
        with col_u1:
            uploaded_manifest = st.file_uploader(
                "Package Manifest (`container.yml`):", type=["yml", "yaml"]
            )
        with col_u2:
            uploaded_source = st.file_uploader(
                "Source Files Bundle (`.zip`):", type=["zip"]
            )

        custom_package_name = st.text_input(
            "Package Name:", placeholder="e.g. image_processor"
        )

        if st.button(
            "Build and Push Package",
            type="primary",
            disabled=(central_ip is None),
        ):
            if not uploaded_manifest or not uploaded_source or not custom_package_name:
                st.error(
                    "Please supply a manifest file, source zip, and package name."
                )
            else:
                brane_cli = get_brane_executable()
                with st.status("Building and registering package...", expanded=True) as status:
                    user_dir = f"/tmp/brane-user-package-{custom_package_name}"
                    if os.path.exists(user_dir):
                        shutil.rmtree(user_dir)
                    os.makedirs(user_dir, exist_ok=True)

                    st.write("Staging source files...")
                    with open(os.path.join(user_dir, "container.yml"), "wb") as f:
                        f.write(uploaded_manifest.getbuffer())

                    zip_path = os.path.join(user_dir, "source.zip")
                    with open(zip_path, "wb") as f:
                        f.write(uploaded_source.getbuffer())
                    with zipfile.ZipFile(zip_path, "r") as zip_ref:
                        zip_ref.extractall(user_dir)
                    for root, dirs, files in os.walk(user_dir):
                        for file in files:
                            os.chmod(os.path.join(root, file), 0o755)

                    st.write("Building package...")
                    build_res = subprocess.run(
                        [brane_cli, "package", "build", "./container.yml"],
                        cwd=user_dir,
                        capture_output=True,
                        text=True,
                    )
                    if build_res.returncode != 0:
                        st.error(f"Build failed:\n{build_res.stderr}")
                        status.update(label="Build failed", state="error")
                        st.stop()

                    st.write(f"Pushing `{custom_package_name}` to registry...")
                    subprocess.run(
                        [brane_cli, "login", f"http://{central_ip}", "--username", "dashboard_user"],
                        capture_output=True,
                        text=True,
                    )
                    push_res = subprocess.run(
                        [brane_cli, "package", "push", custom_package_name],
                        cwd=user_dir,
                        capture_output=True,
                        text=True,
                    )
                    if push_res.returncode == 0:
                        status.update(
                            label=f"Package `{custom_package_name}` registered successfully!",
                            state="complete",
                        )
                        st.success(
                            f"Package is live. Import it in workflows with: "
                            f"`import {custom_package_name};`"
                        )
                    else:
                        status.update(label="Registry push failed", state="error")
                        st.error(f"Registry error:\n{push_res.stderr}")

    # =========================================================================
    # TAB 2: SMOKE TEST
    # =========================================================================
    with tab2:
        st.markdown("Run the baseline hello-world smoke test against the cluster.")

        test_mode = st.selectbox(
            "Runtime:",
            ["Python-based Package (Recommended)", "Bash Shell-based Package"],
        )

        if st.button(
            "Run Hello World Smoke Test",
            type="primary",
            disabled=(central_ip is None),
        ):
            brane_cli = get_brane_executable()
            with st.status("Running smoke test...", expanded=True) as status:
                test_dir = "/tmp/hello-world-test"
                if os.path.exists(test_dir):
                    shutil.rmtree(test_dir)
                os.makedirs(test_dir, exist_ok=True)

                container_yml_path = os.path.join(test_dir, "container.yml")

                if "Python" in test_mode:
                    st.write("Preparing Python package...")
                    script_path = os.path.join(test_dir, "analyze.py")
                    with open(script_path, "w") as f:
                        f.write(
                            '#!/usr/bin/env python3\nimport yaml\n'
                            'print(yaml.dump({"output": "Hello from Python!"}, '
                            'default_flow_style=True).strip())\n'
                        )
                    os.chmod(script_path, 0o755)
                    with open(container_yml_path, "w") as f:
                        f.write(
                            "name: python_hello\nversion: 1.0.0\nkind: ecu\n"
                            "dependencies:\n - python3\n - python3-yaml\n"
                            "files:\n - analyze.py\nentrypoint:\n kind: task\n exec: analyze.py\n"
                            "actions:\n 'hello':\n  command:\n  input:\n  output:\n"
                            "   - name: output\n     type: string\n"
                        )
                    package_name = "python_hello"
                    workflow = "import python_hello;\nprint(python_hello.hello());\n"
                else:
                    st.write("Preparing Bash package...")
                    script_path = os.path.join(test_dir, "hello_world.sh")
                    with open(script_path, "w") as f:
                        f.write('#!/bin/bash\necho \'output: "Hello from Bash!"\'\n')
                    os.chmod(script_path, 0o755)
                    with open(container_yml_path, "w") as f:
                        f.write(
                            "name: bash_hello\nversion: 1.0.0\nkind: ecu\n"
                            "files:\n - hello_world.sh\nentrypoint:\n kind: task\n exec: hello_world.sh\n"
                            "actions:\n 'hello_world':\n  command:\n  input:\n  output:\n"
                            "   - name: output\n     type: string\n"
                        )
                    package_name = "bash_hello"
                    workflow = "import bash_hello;\nprint(bash_hello.hello_world());\n"

                st.write("Building package...")
                build_res = subprocess.run(
                    [brane_cli, "package", "build", "./container.yml"],
                    cwd=test_dir,
                    capture_output=True,
                    text=True,
                )
                if build_res.returncode != 0:
                    st.error(f"Build failed:\n{build_res.stderr}")
                    status.update(label="Build failed", state="error")
                    st.stop()

                st.write("Pushing to registry...")
                subprocess.run(
                    [brane_cli, "login", f"http://{central_ip}", "--username", "smoke_tester"],
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    [brane_cli, "package", "push", package_name],
                    cwd=test_dir,
                    capture_output=True,
                    text=True,
                )

                workflow_file = os.path.join(test_dir, "workflow.bs")
                with open(workflow_file, "w") as f:
                    f.write(workflow)

                st.write("Running workflow...")
                run_res = subprocess.run(
                    [
                        brane_cli, "workflow", "run", "workflow.bs",
                        "--remote", f"http://{central_ip}:50053",
                    ],
                    cwd=test_dir,
                    capture_output=True,
                    text=True,
                )

                if run_res.returncode == 0:
                    status.update(label="Smoke test passed!", state="complete")
                    st.subheader("Output")
                    st.code(run_res.stdout, language="yaml")
                else:
                    status.update(label="Smoke test failed", state="error")
                    st.error(f"Workflow error:\n{run_res.stderr}")

