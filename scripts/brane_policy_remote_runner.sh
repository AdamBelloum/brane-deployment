#!/usr/bin/env bash
# Executes one policy operation inside a selected checker network namespace.
# Arguments:
#   1 checker container
#   2 worker node.yml
#   3 checker address
#   4 staged JWT file
#   5 operation: add | activate | list
#   6 optional payload: policy path or version

set -u
set -o pipefail

checker_container="$1"
node_config="$2"
checker_address="$3"
token_file="$4"
operation="$5"
payload="${6:-}"

cleanup() {
    rm -f -- "${token_file}"
}
trap cleanup EXIT

[[ -f "${node_config}" ]] || {
    echo "ERROR: node configuration not found: ${node_config}" >&2
    exit 2
}

pid="$(docker inspect -f '{{.State.Pid}}' "${checker_container}")" || {
    echo "ERROR: checker container not found: ${checker_container}" >&2
    exit 2
}

[[ "${pid}" != "0" ]] || {
    echo "ERROR: checker container is not running: ${checker_container}" >&2
    exit 2
}

token="$(<"${token_file}")"
cmd=("${HOME}/.local/bin/branectl" policies "${operation}")

case "${operation}" in
    add)
        cmd+=("${payload}")
        ;;
    activate)
        [[ -n "${payload}" ]] && cmd+=("${payload}")
        ;;
    list)
        ;;
    *)
        echo "ERROR: unsupported policy operation: ${operation}" >&2
        exit 2
        ;;
esac

cmd+=(--node-config "${node_config}" --address "${checker_address}")

export LC_ALL=C
export LANG=C

#sudo nsenter --target "${pid}" --net -- \
#    env "LC_ALL=C" "LANG=C" "TOKEN=${token}" "${cmd[@]}"
if [[ -t 0 && -r /dev/tty ]]; then
    # Explicitly bind interactive branectl prompts to the SSH pseudo-terminal.
    # Do not use exec: the EXIT trap must remove the staged JWT afterwards.
    sudo nsenter --target "${pid}" --net -- \
        env "LC_ALL=C" "LANG=C" "TOKEN=${token}" "${cmd[@]}" \
        </dev/tty
else
    sudo nsenter --target "${pid}" --net -- \
        env "LC_ALL=C" "LANG=C" "TOKEN=${token}" "${cmd[@]}"
fi
