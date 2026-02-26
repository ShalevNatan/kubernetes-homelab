# CLAUDE.md — kubernetes-homelab

This file is read by Claude Code at the start of every session in this repo.
Read it fully before doing anything.

---

## Who You Are Working With

Shalev is a DevOps engineer on an 8-month learning journey targeting senior DevOps / Platform Engineering roles. This repo is both a deep learning environment and a portfolio project. Every decision, mistake, and fix is intentionally visible in Git history — that's not sloppiness, that's the point.

Optimize for deep understanding and engineering quality, not speed.

---

## What This Repo Is

A production-grade Kubernetes homelab running on VMware Workstation Pro on Windows 11 Pro. The goal is a fully automated, well-documented, observable Kubernetes cluster that demonstrates real-world DevOps practices.

**Hardware:** HP ZBook Fury G8 — i7 11th Gen, 64GB RAM, 2TB NVMe  
**Host OS:** Windows 11 Pro (Intel TME enabled, VBS active — native VMware mode not possible)  
**Hypervisor:** VMware Workstation Pro 25H2 (WHP mode)  
**Cluster:** 3 nodes — 1 master (4vCPU/16GB), 2 workers (4vCPU/12GB each)  
**Guest OS:** Ubuntu 24.04.3 LTS  
**Network:** VMnet8 NAT — 192.168.70.0/24  
**K8s:** kubeadm, Kubernetes 1.34.x, containerd runtime, Calico CNI  

---

## Current Stage

**Stages 1–3 complete.** Stage 4 (Core Services) is next.

| Stage | Description | Status |
|-------|-------------|--------|
| 1 | Foundation & VMware template | ✅ Complete |
| 2 | Infrastructure as Code (PowerShell + Ansible) | ✅ Complete |
| 3 | Kubernetes bootstrap (kubeadm, containerd) | ✅ Complete |
| 4 | Core Services (CNI, Ingress, Storage) | 🔄 Next |
| 5 | Observability (Prometheus, Grafana, Loki) | ⬜ Pending |
| 6 | GitOps & CI/CD (ArgoCD) | ⬜ Pending |
| 7 | Advanced Topics (Security, Performance) | ⬜ Pending |
| 8 | Polish & Interview Prep | ⬜ Pending |

Do not suggest implementations from future stages unless explicitly asked.

---

## Repo Structure

```
kubernetes-homelab/
├── CLAUDE.md
├── README.md
├── docs/
│   ├── architecture/
│   │   ├── decisions/          ← ADRs (0001–0011)
│   │   └── diagrams/
│   ├── learning-notes/
│   ├── runbooks/
│   └── setup-guides/
├── infrastructure/
│   ├── ansible/
│   │   ├── ansible.cfg
│   │   ├── inventory/
│   │   │   ├── hosts.ini
│   │   │   └── group_vars/all.yml
│   │   ├── playbooks/          ← 01 through 05 currently
│   │   ├── roles/
│   │   └── templates/
│   └── powershell/             ← provision-vms.ps1, deprovision-vms.ps1
├── kubernetes/
│   ├── apps/
│   ├── bootstrap/
│   ├── core/
│   └── gitops/
├── scripts/
│   ├── kubernetes/
│   └── utilities/
├── tests/
└── tools/
    └── lab-dashboard/          ← in-progress: FastAPI + HTML control plane
```

---

## Stack Decisions — Do Not Re-Open These

These are documented in ADRs. Do not suggest alternatives unless asked.

- **Hypervisor:** VMware Workstation Pro — not VirtualBox, not Hyper-V
- **Provisioning:** PowerShell + vmrun.exe — not Terraform (VMware provider has critical bugs, see ADR-0005)
- **Config management:** Ansible — not Chef, not Puppet
- **K8s distribution:** kubeadm — not k3s, not RKE2, not kind
- **Container runtime:** containerd — not Docker
- **CNI:** Calico — not Flannel, not Cilium
- **Ansible execution:** runs from WSL2 on the Windows host — not from inside the VMs

---

## Critical Environment Constraints

These have caused real problems. Respect them.

**Windows / WSL2 boundary:**
- Never write files across the WSL2 / Windows filesystem boundary — causes corruption
- SSH keys must be WSL2-native (created inside WSL2, stored in WSL2 home)
- Ansible runs from WSL2 — paths inside playbooks are Linux paths

**VMware networking:**
- NAT gateway is at 192.168.70.2, not 192.168.70.1
- VMnet8 is the NAT adapter — do not assume bridged networking

**VMware WHP mode:**
- Hardware-enforced VBS on this machine means VMware runs in WHP (Windows Hypervisor Platform) mode
- Nested virtualization is limited — do not suggest configurations that require full nested virt

---

## Design Principles

These apply to everything built in this repo.

**Discover, don't hardcode** — if something is dynamic (playbook list, VM names, config values), read it from the filesystem or a config file. Never hardcode lists that will change over time.

**Scripts must remain standalone** — the lab dashboard orchestrates scripts, it does not replace them. Every PowerShell script and Ansible playbook must be runnable without the dashboard.

**Fail visibly, never silently** — errors must surface to the operator. No swallowed exceptions, no silent failures.

**Automation-first, understanding-always** — automation is the goal, but not at the cost of understanding why it works. Explain non-obvious decisions in comments.

**Document decisions, not just outcomes** — ADRs live in `docs/architecture/decisions/`. When a significant technical choice is made, it gets an ADR. The next ADR number is 0012.

---

## Documentation Standards

- ADRs follow the template at `docs/architecture/decisions/template.md`
- Runbooks go in `docs/runbooks/`
- Learning notes go in `docs/learning-notes/`
- All docs are markdown, suitable for direct Git commit
- Write documentation as if a competent engineer unfamiliar with this specific setup will read it

---

## Git Discipline

- Commit messages are descriptive, not lazy ("fix bug" is not acceptable)
- The Git history is part of the portfolio — it should tell a coherent story
- Mistakes followed by fixes are intentional and valuable — do not squash them away

---

## What Good Output Looks Like Here

- Inline comments explaining *why*, not just *what*
- Code that a senior engineer would not be embarrassed by
- Configurations that reflect real-world patterns, not tutorial shortcuts
- Documentation that would survive a technical interview question about any decision made
