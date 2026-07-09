#!/bin/bash
# A simple audit script for your roles
echo "Linting all roles..."
for role in roles/*; do
  if [ -d "$role" ]; then
    ansible-lint "$role/tasks/main.yml"
  fi
done
