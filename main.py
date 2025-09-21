import os
import json
import subprocess
import paramiko
from dotenv import load_dotenv
import time
from pathlib import Path
import logging

# -------------------
# Setup logging
# -------------------
logger = logging.getLogger("vm_manager")
logger.setLevel(logging.DEBUG)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# File handler
log_file_path = os.path.join(os.getcwd(), "vm_manager.log")
fh = logging.FileHandler(log_file_path)
fh.setLevel(logging.DEBUG)

# Formatter
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
fh.setFormatter(formatter)

# Add handlers
logger.addHandler(ch)
logger.addHandler(fh)

# -------------------
# Load environment
# -------------------
load_dotenv()

BASE_VM_DIR = os.getenv("BASE_VM_DIR")
BASE_VM_PATH = os.getenv("BASE_VM_PATH")
BASE_VM_USERNAME = os.getenv("BASE_VM_USERNAME")
BASE_VM_PASSWORD = os.getenv("BASE_VM_PASSWORD")


# -------------------
# VM functions
# -------------------
def create_vms():
    with open("vms.json", "r") as f:
        vms = json.load(f)

    for vm in vms:
        name = vm["name"]
        path = vm.get("path")
        ip = vm.get("ip")

        if path is not None and ip is not None and not os.path.exists(path):
            vm["path"] = None
            vm["ip"] = None

        if path is None or ip is None:
            vm_path = os.path.join(BASE_VM_DIR, name, f"{name}.vmx")
            clone_cmd = [
                "vmrun",
                "clone",
                BASE_VM_PATH,
                vm_path,
                "full",
                "--cloneName=" + name,
            ]

            logger.info(f"Cloning VM {name}...")
            subprocess.run(clone_cmd, check=True)

            start_cmd = ["vmrun", "start", vm_path, "gui"]
            logger.info(f"Starting VM {name}...")
            subprocess.run(start_cmd, check=True)

            logger.info(f"Waiting for VM {name} to get IP...")
            while True:
                time.sleep(1)
                ip_cmd = ["vmrun", "getGuestIPAddress", vm_path, "-wait"]
                try:
                    ip = subprocess.check_output(ip_cmd).decode().strip()
                    if ip:
                        break
                except subprocess.CalledProcessError:
                    continue

            vm["path"] = vm_path
            vm["ip"] = ip

            with open("vms.json", "w") as f:
                json.dump(vms, f, indent=4)

            logger.info(f"VM {name} is ready at IP {ip}")


def configure_ansible_master():
    with open("vms.json", "r") as f:
        vms = json.load(f)

    ansible_master_ip = None
    for vm in vms:
        if vm["name"] == "Control-Plane":
            ansible_master_ip = vm["ip"]
            break

    if ansible_master_ip is None:
        logger.critical("Control Plane has no IP")
        exit(1)
        return

    # Remove Control Plane from target hosts
    target_vms = [
        vm for vm in vms if vm["name"] != "Control-Plane" and vm["state"] == "start"
    ]

    logger.info("Connecting to Control Plane via SSH...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ansible_master_ip, username=BASE_VM_USERNAME, password=BASE_VM_PASSWORD)

    commands = [
        "apt-get install -y ansible ansible-core python3-pip sshpass tree jq 7zip nmap",
        "ansible-galaxy collection install ansible.posix community.general community.crypto",
        "echo '[defaults]' | tee /root/ansible.cfg",
        "echo 'inventory = /root/inventory' | tee -a /root/ansible.cfg",
        "echo 'deprecation_warnings = False' | tee -a /root/ansible.cfg",
        "echo '[all]' | tee /root/inventory",
    ]

    for vm in target_vms:
        safe_name = vm["name"].replace(" ", "-")
        commands.append(
            f"echo '{safe_name} ansible_host={vm['ip']} ansible_python_interpreter=/usr/bin/python3' | tee -a /root/inventory"
        )
        commands.append(f"echo '{vm['ip']} {safe_name}' | tee -a /etc/hosts")

    for cmd in commands:
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        out, err = stdout.read().decode(), stderr.read().decode()
        if out:
            logger.info(f"Command {cmd} executed successfully")
        elif err:
            logger.error(f"Command {cmd} failed: {err}")
            exit(1)
        elif exit_status != 0:
            logger.critical(f"Command failed: {cmd}")
            exit(1)

    # SSH key generation and copy
    logger.info("Generating SSH key and copying to target VMs...")
    ssh.exec_command("mkdir /root/.ssh/")
    ssh.exec_command("touch /root/.ssh/id_rsa")
    ssh.exec_command("chmod 0600 /root/.ssh/id_rsa")
    ssh.exec_command("ssh-keygen -t rsa -b 2048 -f /root/.ssh/id_rsa -q -N '' -y")

    for vm in target_vms:
        cmd = f"sshpass -p '{BASE_VM_PASSWORD}' ssh-copy-id -f -o StrictHostKeyChecking=no {BASE_VM_USERNAME}@{vm['ip']}"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        out, err = stdout.read().decode(), stderr.read().decode()
        if out:
            logger.info(f"Command {cmd} executed successfully")
        elif err:
            logger.error(f"Command {cmd} failed")
            exit(1)
        elif exit_status != 0:
            logger.critical(f"Failed to copy SSH key to {vm['name']}")
            exit(1)

    ssh.close()
    logger.info("Control Plane configuration complete.")


def boot_all_vms():
    with open("vms.json", "r") as f:
        vms = json.load(f)

    for vm in [v for v in vms if v.get("state", "stop") == "start"]:
        path = vm.get("path")
        if path:
            logger.info(f"Booting VM {vm['name']}...")
            subprocess.run(["vmrun", "start", path, "gui"], check=True)

    # time.sleep(20)


def stop_all_vms():
    with open("vms.json", "r") as f:
        vms = json.load(f)

    for vm in vms:
        path = vm.get("path")
        if path:
            logger.info(f"Stopping VM {vm['name']}...")
            subprocess.run(["vmrun", "stop", path, "hard"], check=True)


def execute_playbooks():
    with open("vms.json", "r") as f:
        vms = json.load(f)

    ansible_master_ip = next(
        (vm["ip"] for vm in vms if vm["name"] == "Control-Plane"), None
    )

    if not ansible_master_ip:
        logger.error("Control Plane has no IP")
        return

    logger.info("Connecting to Control Plane to execute playbooks...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ansible_master_ip, username=BASE_VM_USERNAME, password=BASE_VM_PASSWORD)

    sftp = ssh.open_sftp()
    local_playbooks_dir = Path("playbooks")
    remote_playbooks_dir = "/root/playbooks"

    try:
        sftp.mkdir(remote_playbooks_dir)
    except IOError:
        pass

    for item in local_playbooks_dir.iterdir():
        if item.is_file() and item.suffix in {".yml", ".yaml"}:
            logger.info(f"Uploading {item.name} to Control Plane...")
            sftp.put(str(item), f"{remote_playbooks_dir}/{item.name}")

    sftp.close()

    # Load playbooks.json
    with open("playbooks.json", "r") as f:
        playbooks = json.load(f)

    # Loop over JSON config
    for pb in playbooks:
        # Check flags
        if pb.get("execute_deletion", False):
            cmd = f"ansible-playbook {remote_playbooks_dir}/{pb['deletion']}"
            logger.info(f"Executing deletion for {pb['name']}...")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            stdout.channel.recv_exit_status()
            out, err = stdout.read().decode(), stderr.read().decode()
            if out:
                logger.info(f"Deletion playbook executed successfully for {pb['name']}")
            if err:
                logger.critical(f"Deletion playbook failed for {pb['name']}: {err}")

        if pb.get("execute_installation", False):
            cmd = f"ansible-playbook {remote_playbooks_dir}/{pb['installation']}"
            logger.info(f"Executing installation for {pb['name']}...")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            stdout.channel.recv_exit_status()
            out, err = stdout.read().decode(), stderr.read().decode()
            if out:
                logger.info(
                    f"Installation playbook executed successfully for {pb['name']}"
                )
            if err:
                logger.critical(f"Installation playbook failed for {pb['name']}: {err}")

    ssh.close()
    logger.info("All playbooks executed.")


if __name__ == "__main__":
    # create_vms()
    # boot_all_vms()
    # configure_ansible_master()
    execute_playbooks()
    # stop_all_vms()
    ...
