# ADR-004: VM Storage Layout Structure

**Status**: Accepted  
**Date**: 2026-01-01  
**Deciders**: Shalev Natan  
**Technical Story**: Stage 1 - Foundation & VMware Setup

## Context

VMware Workstation Pro defaults to storing all VMs in a single flat directory (e.g., `D:\VMs`). For a long-term homelab project spanning multiple VM types—templates, production nodes, and future testing environments—we need a storage organization strategy that supports:

- Logical separation of VM lifecycle stages (immutable templates vs. stateful workloads)
- Efficient backup and snapshot management
- Clean Infrastructure as Code (IaC) path references
- Future lab expansion without reorganization

The homelab runs on a single physical machine with a dedicated 1.8TB D:\ drive for all VM storage.

## Decision

**VM storage will follow a two-level hierarchical structure under a unified homelab root**:
```
D:\homelab\
├── iso\                    # Installation media
├── vms\
│   ├── templates\          # Immutable golden images
│   └── cluster\            # Stateful Kubernetes nodes
├── backups\                # Snapshots and exports
└── scripts\                # Automation tooling
```

**VMware Workstation global default**: `D:\homelab\vms`  
**Template path**: `D:\homelab\vms\templates\k8s-template\`  
**Cluster nodes**: `D:\homelab\vms\cluster\k8s-{master|worker}-NN\`

## Non-Goals

This structure does **not** aim to:
- Optimize for multi-tenant access control (single-user homelab)
- Support VMs across multiple physical drives (single D:\ drive)
- Mirror cloud provider organizational models (prioritizes local simplicity)

## Rationale

### Separation Enables Targeted Policies
- **Templates**: Backup once post-creation, exclude from nightly snapshots
- **Cluster VMs**: Daily snapshots, disaster recovery automation
- **Future categories** (staging, dev): Add as sibling directories without refactoring

### IaC Integration
Terraform and Ansible benefit from structured, predictable paths:
```hcl
# Terraform variable
variable "template_path" {
  default = "D:/homelab/vms/templates"
}
```
```yaml
# Ansible inventory mapping
[k8s_cluster]
k8s-master-01  ansible_host=192.168.70.11  vm_path=/homelab/vms/cluster/k8s-master-01
```

Scripts can target categories (`D:\homelab\vms\cluster\*`) without hardcoding VM names.

### Portfolio Signal
Demonstrates infrastructure thinking beyond immediate requirements:
- Anticipates growth (staging, testing environments)
- Applies production separation principles (immutable infrastructure)
- Shows IaC-first mindset before writing automation code

## Alternatives Considered

### Alternative 1: Flat Structure (VMware Default)
**Path**: `D:\VMs\k8s-template`, `D:\VMs\k8s-master-01`, ...

**Rejected because**:
- No logical grouping—all VMs treated identically
- Backup policies must target individual VMs, not categories
- Scales poorly (20+ VMs become unmanageable)
- Misses opportunity to demonstrate architectural planning

### Alternative 2: Deep Hierarchy
**Path**: `D:\homelab\vms\kubernetes\production\cluster\control-plane\k8s-master-01\`

**Rejected because**:
- Premature abstraction (single cluster, no multi-environment need)
- Long paths complicate CLI operations and scripts
- No current requirement justifies added complexity

### Alternative 3: Category-per-Drive
**Paths**: Templates on `D:\`, Cluster on `E:\`, Backups on `F:\`

**Rejected because**:
- Requires multiple drives (not available)
- Complicates path management across tooling
- Over-optimization for I/O performance not needed at homelab scale

## Consequences

### Positive
- Clear organization from project start—no future reorganization debt
- Backup automation can target directories: `D:\homelab\vms\cluster\*` → nightly snapshots
- IaC references remain stable as lab grows
- Interview narrative: "Designed for scale before implementing first VM"

### Negative
- Requires manual path specification during VM creation (one-time, 10 seconds per VM)
- Diverges from VMware defaults (mitigated: global setting updated)

### Neutral
- Single directory level added vs. flat structure
- All homelab artifacts centralized under `D:\homelab\`

## Implementation

### Configuration
```powershell
# VMware Workstation: Edit → Preferences → Workspace
# Set: Default location for virtual machines = D:\homelab\vms
```

### Directory Initialization
```powershell
New-Item -ItemType Directory -Force -Path "D:\homelab\vms\templates"
New-Item -ItemType Directory -Force -Path "D:\homelab\vms\cluster"
New-Item -ItemType Directory -Force -Path "D:\homelab\backups"
New-Item -ItemType Directory -Force -Path "D:\homelab\scripts"
```

### Applied Paths
- **Template**: `D:\homelab\vms\templates\k8s-template\`
- **Production nodes**: `D:\homelab\vms\cluster\k8s-{master|worker}-NN\`
- **ISOs**: `D:\homelab\iso\` (pre-existing)

## Compliance

Aligns with:
- **ADR-001** (Hypervisor Selection): Storage layout hypervisor-agnostic
- **ADR-003** (Network Architecture): Independent of network topology
- **IaC Principles**: Predictable paths, category-based targeting

## Review Cycle

**Triggers for re-evaluation**:
- **Stage 3**: If etcd backups require dedicated directory structure
- **Stage 5**: If persistent volumes necessitate separate storage paths
- **Lab expansion**: When deploying non-Kubernetes VMs (databases, monitoring)
- **Scale threshold**: Exceeding 10 VMs in a single category

**Next scheduled review**: End of Stage 3 or upon deploying 5+ VMs

---

**Implementation Date**: 2026-01-01  
**Last Updated**: 2026-01-02  
**Related ADRs**: ADR-001 (Hypervisor Selection)
