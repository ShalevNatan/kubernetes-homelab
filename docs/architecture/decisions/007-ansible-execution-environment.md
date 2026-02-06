# ADR 007: Ansible Execution Environment - WSL2 vs Native Windows

**Date:** 2026-02-04  
**Status:** Accepted  
**Context:** Stage 2.3 - Configuration Management Setup

## Decision

Use WSL2 Ubuntu with native Ansible installation for configuration management.

## Context

After VM provisioning automation (PowerShell), needed tool for OS-level configuration (static IPs, hostnames, system packages). Evaluated:
- Option A: Ansible in WSL2
- Option B: Ansible on native Windows (via Python)
- Option C: Separate Ansible control VM

## Decision Drivers

1. **Linux tool compatibility** - Ansible modules work best in Linux
2. **SSH key permissions** - Windows filesystem doesn't support Linux permissions (777 issue)
3. **Future tooling** - kubectl, kubeadm, helm also need Linux environment
4. **Portfolio authenticity** - Match production DevOps workflows

## Decision

**Chose WSL2 + Ansible** with:
- WSL2-native SSH keys (`~/.ssh/homelab_wsl`)
- Ansible config in WSL2 home (`~/.ansible.cfg`)
- Playbooks stored on Windows filesystem (`/mnt/d/homelab/ansible/`)
- Separation of concerns: Windows for VM management, WSL2 for VM configuration

## Consequences

### Positive
- Native Linux tooling without hypervisor overhead
- SSH keys work properly with correct permissions
- Ansible modules behave as documented
- Ready for Stage 3 (Kubernetes tooling)
- Portfolio shows Linux proficiency

### Negative
- Filesystem crossing (Windows ↔ WSL2) requires care
- Caused D: drive corruption during initial SSH key copy
- Learned: Never copy files between filesystems, only read

### Mitigation
- **Rule:** WSL2 only reads from `/mnt/d/`, never writes to VM directories
- **Rule:** Create WSL2-native keys, reference Windows keys read-only
- **Rule:** Ansible playbooks in `/mnt/d/` (version controlled), config in WSL2 home

## Lessons Learned

1. **Interface discovery matters** - Template assumed `ens160`, VMs had `ens32`
2. **Idempotency is critical** - Playbooks ran multiple times during debugging
3. **Automation paradox** - Inventory update task couldn't run after IP change (chicken-egg)
4. **Dry-run discipline** - Always `--check` before applying changes

## Related Decisions
- ADR-003: VMware Workstation hypervisor choice
- ADR-005: Network architecture (VMnet8 NAT)
