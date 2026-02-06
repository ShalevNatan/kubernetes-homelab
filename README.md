# Kubernetes Home Lab

A production-grade, multi-node Kubernetes cluster built from scratch on VMware Workstation Pro. This project demonstrates hands-on experience with cloud-native technologies, infrastructure automation, and DevOps practices.

## 🏗️ Architecture
```
┌─────────────────────────────────────────────────────────┐
│  Windows 11 Pro (Host)                                  │
│  HP ZBook Fury G8 - 64GB RAM - 2TB NVMe                │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  VMware Workstation Pro 25H2 (WHP Mode)        │   │
│  │                                                 │   │
│  │  Network: VMnet8 NAT (192.168.70.0/24)        │   │
│  │  ┌──────────────┐  ┌──────────────┐           │   │
│  │  │ k8s-master   │  │ k8s-worker-1 │           │   │
│  │  │ .70.10       │  │ .70.11       │           │   │
│  │  │ 16GB RAM     │  │ 16GB RAM     │           │   │
│  │  │ 4 vCPU       │  │ 4 vCPU       │           │   │
│  │  └──────────────┘  └──────────────┘           │   │
│  │         ┌──────────────┐                       │   │
│  │         │ k8s-worker-2 │                       │   │
│  │         │ .70.12       │                       │   │
│  │         │ 16GB RAM     │                       │   │
│  │         │ 4 vCPU       │                       │   │
│  │         └──────────────┘                       │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Technical Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Hypervisor** | VMware Workstation Pro 25H2 | Type-2 virtualization (WHP mode) |
| **Guest OS** | Ubuntu 24.04.3 LTS Server | Minimal server installation |
| **Container Runtime** | containerd | CRI-compliant runtime |
| **Kubernetes** | kubeadm (vanilla K8s) | Control plane bootstrap |
| **Network Plugin (CNI)** | TBD - Calico or Cilium | Pod networking |
| **Ingress** | TBD - NGINX or Traefik | L7 load balancing |
| **Storage** | TBD - Local PV or Longhorn | Persistent volumes |
| **Load Balancer** | MetalLB | Bare-metal LB (192.168.70.200-250) |
| **GitOps** | ArgoCD | Declarative deployment |
| **Monitoring** | Prometheus + Grafana | Metrics and visualization |
| **Logging** | Loki + Promtail | Log aggregation |
| **IaC** | Terraform + Ansible | Infrastructure automation |

---

## 📁 Repository Structure
```
kubernetes-homelab/
├── docs/                      # Documentation and architecture decisions
│   ├── architecture/          # ADRs, diagrams, design docs
│   ├── runbooks/              # Operational procedures
│   └── setup-guides/          # Step-by-step installation guides
├── infrastructure/            # Infrastructure as Code
│   ├── terraform/             # VM provisioning configurations
│   └── ansible/               # OS configuration playbooks
├── kubernetes/                # Kubernetes manifests and configs
│   ├── bootstrap/             # Cluster initialization
│   ├── core/                  # CNI, Ingress, Storage
│   ├── apps/                  # Monitoring, logging, demo apps
│   └── gitops/                # ArgoCD configurations
├── scripts/                   # Automation scripts
│   ├── vm-management/         # VM lifecycle scripts
│   └── kubernetes/            # Cluster health checks, backups
└── tests/                     # Integration tests and benchmarks
```

---

## 🎯 What This Project Demonstrates

### Infrastructure Skills
- **Virtualization:** VMware Workstation configuration, network design, resource allocation
- **Infrastructure as Code:** Terraform for VM provisioning, Ansible for configuration management
- **Networking:** Static IP allocation, NAT configuration, CNI plugin setup

### Kubernetes Administration
- **Cluster Bootstrap:** Manual kubeadm installation (not managed distributions)
- **Core Services:** CNI, Ingress controllers, storage provisioners, load balancers
- **Observability:** Prometheus metrics, Grafana dashboards, centralized logging
- **GitOps:** ArgoCD for declarative application deployment

### DevOps Practices
- **Documentation:** Architecture Decision Records (ADRs), runbooks, troubleshooting guides
- **Version Control:** Git workflow, meaningful commit history
- **Automation:** Scripted VM management, cluster operations
- **Testing:** Integration tests, performance benchmarks

---

## 🚀 Current Progress

**Stage 1: Foundation** ✅ In Progress
- [x] VMware Workstation configuration
- [x] Network architecture (VMnet8 NAT)
- [x] Git repository structure
- [x] Ubuntu 24.04 LTS template VM
- [x] Initial ADRs (hypervisor, memory, networking)

**Stage 2: Infrastructure as Code** 🔜 Upcoming
- [x] ~~Terraform VM provisioning~~ No stable Terraform provider found, Moved to PowerShell
- [ ] Ansible playbooks (Static IPs, OS hardening, container runtime)
- [ ] Automated node deployment

**Stage 3: Kubernetes Bootstrap** 🔜 Planned
- [ ] kubeadm cluster initialization
- [ ] Control plane configuration
- [ ] Worker node joining

**Stages 4-8:** Core services, observability, GitOps, security hardening, performance tuning

---

## 📚 Key Learnings & Highlights

_This section will be updated as the project progresses with interesting challenges, solutions, and insights gained during the build process._

### Foundation Phase
- **Challenge:** Windows Hypervisor Platform (WHP) mode limitations vs. native Intel VT-x
- **Solution:** Accepted performance trade-off to maintain system security (VBS/TPM)
- **Learning:** Real-world constraints require pragmatic architecture decisions

---

## 🔧 Quick Start

_(Will be populated with deployment instructions as automation scripts are completed)_

### Prerequisites
- VMware Workstation Pro 25H2 or later
- 64GB RAM minimum (48GB allocated to VMs)
- 500GB free disk space (SSDs recommended)

### Deployment
```bash
# Clone repository
git clone <repository-url>
cd kubernetes-homelab

# Deploy infrastructure (Coming in Stage 2)
cd infrastructure/terraform/vmware
terraform init
terraform apply

# Configure nodes (Coming in Stage 2)
cd ../../ansible
ansible-playbook -i inventory/hosts.yml playbooks/bootstrap-nodes.yml

# Initialize cluster (Coming in Stage 3)
# Instructions to be added
```

---

## 📖 Documentation

- **[Architecture Decisions](docs/architecture/decisions/)** - ADRs documenting major technical choices
- **[Setup Guides](docs/setup-guides/)** - Detailed installation procedures
- **[Runbooks](docs/runbooks/)** - Operational procedures and troubleshooting

---

## 🎓 About This Project

This lab represents an 8-month hands-on learning journey through modern DevOps and cloud-native technologies. Built entirely on local hardware to simulate on-premises infrastructure, it demonstrates the ability to design, deploy, and operate production-grade Kubernetes environments from first principles.

The project emphasizes:
- **Deep understanding** over quick wins - every component installed manually before automation
- **Real-world constraints** - working within hardware limits, Windows compatibility issues
- **Production practices** - monitoring, logging, disaster recovery, documentation
- **Continuous improvement** - iterative refinement based on lessons learned

---

## 📝 License

This project is personal educational work. Documentation and configurations are provided as-is for learning purposes.

---

**Last Updated:** December 2025  
**Current Stage:** 1 of 8 (Foundation)
