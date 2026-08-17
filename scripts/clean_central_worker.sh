#!/usr/bin/env bash
# clean_brane.sh - Completely purge Brane cluster states from Docker
# to execute on the brane central node

echo "=== Stopping and removing Brane containers ==="
BRANE_CONTAINERS=$(docker ps -a --filter "name=brane" -q)
if [ -n "$BRANE_CONTAINERS" ]; then
    docker rm -f $BRANE_CONTAINERS
else
    echo "No Brane containers found."
fi

echo "=== Removing Brane volumes ==="
BRANE_VOLUMES=$(docker volume ls --filter "name=brane" -q)
if [ -n "$BRANE_VOLUMES" ]; then
    docker volume rm $BRANE_VOLUMES
else
    echo "No Brane volumes found."
fi

echo "=== Removing Brane networks ==="
BRANE_NETWORKS=$(docker network ls --filter "name=brane" -q)
if [ -n "$BRANE_NETWORKS" ]; then
    docker network rm $BRANE_NETWORKS
else
    echo "No Brane networks found."
fi

echo "=== System Pruning Docker cache ==="
docker system prune -f

echo "=== Cleaning local directory targets ==="
rm -rf ~/brane-central/config/infra.yml ~/brane-central/config/proxy.yml

echo "Done! The VM environment is clean and ready for Ansible."
