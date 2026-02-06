# Quick Start: Rebuild Cluster from Scratch

## Prerequisites

- VMware Workstation Pro 25H2
- Windows 11 Pro with WSL2
- Template VM snapshot: "Clean Template - v3 (SSH + Sudo)"

## Steps

### 1. Provision VMs (4 minutes)
```powershell
cd D:\homelab\scripts
.\provision-vms.ps1
```

### 2. Configure Static IPs (2 minutes)
```bash
# In WSL2:
cd /mnt/d/homelab/ansible
ansible-playbook playbooks/01-static-networking.yml
```

### 3. Configure Hostnames (1 minute)
```bash
ansible-playbook playbooks/02-configure-hostnames.yml
```

### 4. Verify Cluster (30 seconds)
```bash
ansible all -m ping
ansible all -m command -a "hostname"
ansible all -m command -a "ping -c 2 k8s-master-01"
```

**Total Time:** ~7 minutes from zero to configured cluster

## Teardown
```powershell
cd D:\homelab\scripts
.\deprovision-vms.ps1 -Force
```
