import os
import subprocess
from flask import Flask, request, Response

app = Flask(__name__)

# Dynamically calculate the path to your docker-deployment folder
ANSIBLE_DIR = os.path.abspath("../brane-depoyment/docker-deployment/")

# CHANGE HERE: Add 'GET' to the allowed methods array so Flask won't drop the connection
@app.route('/deploy-brane', methods=['GET', 'POST'])
@app.route('/deploy-brane/', methods=['GET', 'POST'])
def run_ansible():     
    # If Appsmith probes with a GET, give it a quick status report
    if request.method == 'GET':
        print("⚠️ Received a GET request instead of a POST!")
        return "Backend is ready! Please send a POST request with your configuration JSON.", 200
        
    # Otherwise, execute your normal Ansible process for POST
    data = request.json or {}
    tags = data.get('tags', [])
    extra_vars = data.get('vars', {})

# Target the explicit production hosts file you just found
    inventory_path = os.path.join(ANSIBLE_DIR, 'inventories/production/hosts.ini')
    cmd = ['ansible-playbook', '-i', inventory_path, 'deploy-brane.yml']
    if tags:
        cmd.extend(['--tags', ','.join(tags)])
        
    for key, val in extra_vars.items():
        val_str = str(val).lower() if isinstance(val, bool) else str(val)
        cmd.extend(['-e', f"{key}={val_str}"])
        
    def generate():
        print(f"🚀 Executing: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd, cwd=ANSIBLE_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )   
        for line in iter(process.stdout.readline, ''):
            yield line
        process.stdout.close()
        
    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
