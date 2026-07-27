---
# Brane Deployment Troubleshooting Guide


**Date:** 2026-07-26
**Host:** ab-01.lab.uvalight.net
**Reporter:** adam


## 1. Issue: `branectl start proxy` fails due to un-sanitized version tag (`+` symbol)

### **The Problem**
When attempting to run `branectl start proxy` using the `3.0.0-nightly+fdbbd6c2` build, the execution fails during the `docker compose up` phase. 

The underlying issue is that `branectl` dynamically writes a temporary Docker Compose configuration file (e.g., `/tmp/docker-compose-proxy*.yml`) and inserts the literal image reference tag containing a plus sign (`+`): `brane-prx:3.0.0-nightly+fdbbd6c2`. Because the `+` character is an illegal symbol according to the OCI/Docker image reference format specifications, the Docker daemon rejects the file outright with an `invalid reference format` error.

### **Error Output**
```text
Running 'docker compose' up on /tmp/docker-compose-proxyv7EyZw.yml...
unable to get image 'brane-prx:3.0.0-nightly+fdbbd6c2': Error response from daemon: invalid reference format
ERROR: Command 'BRANE_IMAGE_VERSION="3.0.0-nightly_fdbbd6c2" BRANE_VERSION="3.0.0-nightly+fdbbd6c2" ... "docker" "compose" "up" "-d"' failed with exit code 1

```

### **Root Cause Analysis**

1. While `branectl` correctly sets the environment variable `BRANE_IMAGE_VERSION="3.0.0-nightly_fdbbd6c2"` (replacing the plus sign with a safe underscore), it incorrectly embeds the un-sanitized `BRANE_VERSION` string containing the `+` directly into the generated YAML's `image:` property block.
2. Because the binary generates this temporary file on the fly and invokes Docker Compose directly, external environment variable overrides or runtime modifications cannot intercept or fix the bad string inside the file.

### **Suggested Fix for Developers**

In the Rust source code responsible for compiling the proxy configuration template, the version string needs to pass through the same sanitation filter used for `BRANE_IMAGE_VERSION`. Any occurrences of the `+` build metadata separator should be automatically replaced with an underscore `_` before the final string is written to the `/tmp/docker-compose-proxy*.yml` manifest file.

---

## 2. Issue: Host File System Permissions (`Permission Denied` / `500 Internal Server Error`)

### **The Problem**

The software inside the Brane Docker containers runs under an isolated internal user ID (**UID 1000**). When the container tries to write files (packages, configurations, or certificates) to the shared volumes mapped on your host machine, the Linux kernel checks permissions.

It sees that your host user account owns the folder, not UID 1000. Because the container user lacks writing rights, the kernel blocks the process, resulting in immediate application crashes or a `Permission Denied` runtime error.

### **The Bad Fix (`chmod 777`)**

Changing permissions globally to `777` opens the folder doors completely. It tells the operating system, *"Anyone, anywhere on this machine, can read, write, or delete files in this folder."* While it gets the container working temporarily, it introduces a severe security vulnerability on production servers.

### **The Proper Fix (POSIX ACLs)**

Instead of throwing the doors wide open, the configuration employs **Access Control Lists (ACLs)**. Think of this like adding a specific line item to the folder's security guest list without modifying basic system ownership:

* **Standard Access:** Tells the kernel, *"Keep the host user as the primary owner, but specifically allow UID 1000 to read, write, and execute files here."*
* **Default Access (Inheritance):** Adds a recursive rule, *"Any new subfolder or file created inside this directory in the future must automatically grant those same rights to UID 1000."*
* **Benefit:** This allows the container to seamlessly write its packages, configs, and certs without compromising the security of the rest of the server.

### **Playbook Implementation**

You only need to copy-paste this new step block. You do not need to rewrite your files. Open your existing `main.yml` files for the **Central**, **Worker**, and **Proxy** roles, find the spot right after the base deployment directories are created, and paste in this section (ensure you use the correct directory variable path per role):

```yaml
- name: Grant container UID 1000 access to the directory
  become: true
  ansible.posix.acl:
    path: "{{ brane_install_dir }}"
    entity: 1000
    etype: user
    permissions: rwx
    state: present

- name: Set default ACL for future files inheritance
  become: true
  ansible.posix.acl:
    path: "{{ brane_install_dir }}"
    entity: 1000
    etype: user
    permissions: rwx
    default: true
    state: present

```

### **Running Ansible Normally**

Once you save the files, run your usual Ansible deployment command. Ansible is smart (idempotent)—it will see that the directories, Docker installations, and files are already perfect, skip right over them in a few seconds, and only apply the new ACL permissions.

### **Verification**

To verify that the permissions applied correctly on the target machine without even running a container, log into the server node and run:

```bash
getfacl /path/to/your/brane-folder

```

You should see a clear line item indicating `user:1000:rwx`, proving the security guard is officially holding the door open for the Docker container.

## **BraneScript parse error**

### parse error
> `BraneScript parse error: reached end-of-file unexpectedly (Compiler error: unkown error from parser: Nom(Eof))`

even for a **minimal, syntactically valid** BraneScript workflow. This suggests:

- Either the **BraneScript grammar in my version differs from the documented examples**, or
- There is a **parser bug/misconfiguration** in the nightly build I am using.

### **Root Cause Analysis** 

- unknown

### **The Proper Fix **

- could not find one
- Ask developper : I’d like help confirming the correct grammar for this Brane version or diagnosing the parser issue.

## 3. Issue:Brane versions (release vs nigh build)

### Summary

The smoke test script (`scripts/run-smoke-test.sh`) fails consistently at the BraneScript compilation step with a parse error. All infrastructure containers are healthy and the package build/push steps succeed. The failure is isolated to workflow execution. Two distinct root causes were identified: a CLI version mismatch and a port mapping mismatch between the instance registration and the smoke test script.

---

## Environment

| Component | Version / Value |
|---|---|
| `brane` CLI (installed) | `3.0.0-nightly+fdbbd6c2` |
| `brane` CLI (required by instructions) | `v3.0.0` stable |
| `branectl` | `v3.0.0` stable |
| `brane-drv` container | `brane-drv:3.0.0-nightly_fdbbd6c2` |
| Central node | `145.100.130.55` / `ab-01.lab.uvalight.net` |
| Host OS | Ubuntu 24.04 |

---

### Observed Error

```
BraneScript parse error: 0: at line 3:

on "worker-a
    ^
expected ';', found 'worker-a'

ERROR: Compilation of workflow failed (see output above)
```

### Root Cause

The installed `brane` CLI is the **nightly build** (`3.0.0-nightly+fdbbd6c2`), but the deployment instructions specify the **stable `v3.0.0` release**. These are fundamentally different versions with incompatible CLIs and BraneScript parsers:

| | `v3.0.0` stable | `3.0.0-nightly` |
|---|---|---|
| Run command | `brane run` | `brane workflow run` |
| Build command | `brane build` | `brane package build` |
| Push command | `brane push` | `brane package push` |
| `on` block syntax | `on "x" { }` | unknown / broken |
| `--version` flag | not supported | supported |

The nightly CLI's BraneScript parser rejects the `on "worker-a" { }` syntax regardless of file content, because the grammar changed between the two builds.

### Fix

Replace the nightly CLI with the stable `v3.0.0` binary:

```bash
sudo curl -fsSL https://github.com/BraneFramework/brane/releases/download/v3.0.0/brane-linux-x86_64 \
  -o /usr/local/bin/brane
sudo chmod +x /usr/local/bin/brane
```

Revert the `.bs` files to the original stable syntax (without `do`):

```bash
cat > scripts/smoke-test-package/worker-a.bs << 'EOF'
import brane_smoke_test;

on "worker-a" {
    let result := ping();
    println(result);
}
EOF

cat > scripts/smoke-test-package/worker-b.bs << 'EOF'
import brane_smoke_test;

on "worker-b" {
    let result := ping();
    println(result);
}
EOF
```

---

## Issue 4 – Port Mapping Mismatch Between Instance Registration and Smoke Test Script

### Root Cause

The deployment instructions register the instance using only the hostname, with no explicit port:

```bash
brane instance add 145.100.130.55 --name wscbs-uva --use
```

The stable `v3.0.0` CLI defaults the API port to `50051` and the driver port to `50053`. However, the smoke test script (`run-smoke-test.sh`) constructs the `brane workflow run` (nightly) or `brane run` (stable) call using `INSTANCE_NAME`, which in the nightly CLI is passed as the `<use case>` positional argument — not as a resolved instance with ports.

The nightly `brane instance list` output confirms the registered instance uses explicit ports:

```
NAME                       API                                DRIVER
ab-01.lab.uvalight.net   ab-01.lab.uvalight.net:50051     ab-01.lab.uvalight.net:50053
```

The smoke test script passes `INSTANCE_NAME` directly to `brane workflow run --remote`, bypassing the registered instance configuration entirely. This means port resolution depends on which CLI version is active:

- **Stable `v3.0.0`**: `brane run` uses the selected instance (set via `brane instance select`) — ports are resolved correctly from the instance config.
- **Nightly**: `brane workflow run --remote <use case>` treats the instance name as a use-case registry URL, not a named instance — ports are not resolved.

### Fix

With the stable CLI in place, do not pass `INSTANCE_NAME` to the script. Instead, pre-select the instance as the instructions specify:

```bash
brane instance select wscbs-uva
./scripts/run-smoke-test.sh
```

If the script must target a specific instance non-interactively, update `run_workflow` in `run-smoke-test.sh` to use the stable CLI syntax:

```bash
# stable v3.0.0 syntax
run_workflow() {
  local workflow="$1"
  printf 'Running %s\n' "$(basename "$workflow")"
  brane run --remote "$workflow"
}
```

---

## Steps Taken During Investigation

1. Confirmed all required containers are running (`brane-prx`, `brane-api`, `brane-drv`, ScyllaDB, Kafka).
2. Confirmed `brane-drv` is reachable on `0.0.0.0:50053`.
3. Updated `.bs` syntax from `on "worker-a" { }` to `on "worker-a" do { }` — error persisted.
4. Confirmed file content via `cat -A` — correct, clean Unix line endings, only one copy on disk.
5. Ran `brane workflow run` directly — same parse error regardless of file content or instance name passed.
6. Compared `v3.0.0` stable and nightly CLI help output — confirmed incompatible command structures.
7. Confirmed deployment instructions specify `v3.0.0` stable for both `branectl` and `brane` CLI.

---

## Recommended Next Steps

1. Install `v3.0.0` stable `brane` CLI (see fix above).
2. Revert `.bs` files to original syntax.
3. Select the correct instance: `brane instance select wscbs-uva`.
4. Update `run-smoke-test.sh` to use stable CLI syntax (`brane run` instead of `brane workflow run --remote`).
5. Pin `BRANE_VERSION=3.0.0` in the smoke test script and document that the nightly build is not supported.

