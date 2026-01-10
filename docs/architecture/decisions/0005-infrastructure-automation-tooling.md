# ADR-005: Infrastructure Automation Tooling Selection

**Status**: Accepted  
**Date**: 2026-01-10  
**Decision Makers**: Shalev  
**Supersedes**: Initial Terraform approach  
**Related**: Stage 2 (Infrastructure as Code)

## Context

Stage 2 required automating VM provisioning for a 3-node Kubernetes cluster on VMware Workstation Pro. The goal was to implement Infrastructure as Code (IaC) principles with:

- **Declarative configuration** of VM specifications
- **Repeatable provisioning** for testing and iteration
- **Version-controlled** infrastructure definitions
- **Idempotent operations** (safe to run multiple times)

Initial plan was to use **Terraform** as the industry-standard IaC tool, with the `hashicorp/vmware-workstation` provider for VMware Workstation integration.

### Terraform Evaluation Process

**Attempted configuration** (simplified):
```hcl
# main.tf
terraform {
  required_providers {
    vmware-workstation = {
      source  = "elsudano/vmware-workstation"
      version = "~> 1.0"
    }
  }
}

provider "vmware-workstation" {
  url      = "http://localhost:8697/api"
  username = "$(vmwareUsername)"
  password = "$(vmwarePassword)"
}

resource "vmware_vm" "k8s_master" {
  sourceid     = vmware_vm_snapshot.template.id  # ← BROKEN
  linkedclone  = true
  name         = "k8s-master-01"
  cpus         = 4
  memory       = 16384
}
```

**Testing timeline**:

1. **Version 1.0.3** (Initial attempt)
   - Provider installed successfully
   - VM resource creation appeared to work
   - Snapshot/linked clone support: **BROKEN**
   - Error: `sourceid` parameter not recognized

2. **Version 1.0.4** (Patch attempt)
   - Same snapshot issues
   - Linked clone feature documented but non-functional
   - Full clones work, but unacceptably slow (5+ min/VM)

3. **Version 2.0.0** (Experimental)
   - Attempted newer  release
   - Support is still broken
   - Additional instability due to alpha status

**Critical failure**: Provider claims snapshot support in documentation, but implementation is incomplete/buggy. Without snapshots, must use full clones which:
- Take 5+ minutes per VM (vs <10 seconds for linked clones)
- Consume 50GB per VM (vs ~500MB for linked clones)
- Don't protect the template from corruption
- After trying without Snapshots, I tried to do what the provider said, but it still didn't work, took too much time, I had to find another solution

### Provider Status Investigation

**GitHub repository**: `elsudano/terraform-provider-vmware-workstation`

**Findings**:
- Last meaningful commit: 18+ months ago
- Open issues for snapshot support: Multiple, unresolved
- Community status: Appears abandoned/unmaintained
- VMware Workstation support: Community effort, not official HashiCorp or VMware

**Alternative providers evaluated**:
- `hashicorp/vsphere`: Only for vSphere, not Workstation
- `terraform-providers/vmware`: Deprecated, merged into vsphere
- No other viable VMware Workstation providers exist

### Business Impact

Continuing with a broken Terraform provider would mean:

**Time cost**:
- 5 minutes per full clone × 3 VMs = 15 minutes per provision
- Across 8-month project with ~50 reprovisions = 12.5 hours wasted
- Manual snapshot management adds complexity

**Disk cost**:
- 50GB per full clone × 3 VMs = 150GB per cluster
- Cannot maintain multiple cluster versions simultaneously
- 2TB drive fills quickly with test iterations

**Risk cost**:
- Template corruption risk without snapshots
- Cannot easily test configuration changes
- Harder to demonstrate rapid iteration capability

## Decision

**Adopt hybrid automation approach**:

1. **VM Provisioning**: PowerShell + VMware `vmrun.exe` CLI
2. **Configuration Management**: Ansible

**Rationale**: Leverage VMware's native, stable tooling instead of broken third-party provider.

### Architecture
```
PowerShell (provision-vms.ps1)
├── Clone VMs from snapshot via vmrun.exe
├── Configure hardware (CPU, RAM via .vmx modification)
├── Power on VMs sequentially
├── Detect IP addresses via VMware Tools
└── Generate Ansible inventory

Ansible (Stage 2.3+)
├── Configure static networking
├── Set hostnames
├── Install Kubernetes prerequisites
└── Bootstrap cluster
```

## Rationale

### Why PowerShell + vmrun.exe?

**Technical advantages**:

1. **Native VMware support**
   - `vmrun.exe` ships with VMware Workstation
   - Developed and maintained by VMware
   - Stable API since VMware Workstation 6.x (~2008)

2. **Snapshot support**
   - Fully functional linked clone creation
   - Fast operations (2-5 seconds per clone)
   - Disk-efficient (delta disks only)

3. **Programmatic control**
   - PowerShell provides scripting capabilities
   - Error handling and validation
   - Integration with Windows environment

4. **No external dependencies**
   - No Terraform providers to maintain
   - No version compatibility issues
   - Works with any VMware Workstation version

**Operational advantages**:

1. **Proven reliability**
   - `vmrun` is battle-tested over 15+ years
   - Used by VMware's own automation
   - Extensive documentation and community knowledge

2. **Troubleshooting**
   - Direct command-line interface
   - Clear error messages
   - No abstraction layers hiding issues

3. **Learning value**
   - Demonstrates understanding of underlying APIs
   - Shows tool selection based on requirements, not hype
   - Practical problem-solving over ideological purity

### Why Still Use Ansible?

Ansible remains ideal for:
- **Configuration management** (OS settings, packages)
- **Declarative state** (network config, services)
- **Industry standard** (widely used in production)
- **Agentless** (SSH-based, no client installation)

**Division of responsibilities**:
```
PowerShell:    Infrastructure layer (VMs, hardware)
Ansible:       Configuration layer (OS, applications)
```

This mirrors real-world enterprise architectures:
- Infrastructure provisioning: Cloud provider APIs, Terraform for cloud
- Configuration management: Ansible, Chef, Puppet

## Alternatives Considered

### Option A: Continue with Terraform despite bugs (Rejected)

**Approach**: Use full clones, manage snapshots manually

**Pros**:
- Industry-standard IaC tool
- Familiar to most DevOps teams
- Declarative syntax

**Cons**:
- Broken snapshot support
- 15 minutes per provision cycle
- 150GB disk per cluster
- Workarounds defeat IaC benefits
- Template corruption risk

**Reason for rejection**: Technical limitations outweigh brand recognition. Spending 15 minutes per provision when 30-second solution exists is poor engineering.

---

### Option B: Use Vagrant (Rejected)

**Approach**: Vagrant with VMware Workstation provider

**Pros**:
- Designed for development environments
- Simple Vagrantfile syntax
- Good documentation

**Cons**:
- Adds abstraction layer over vmrun
- Limited production learning value (Vagrant uncommon in prod)
- Still relies on underlying VMware APIs

**Reason for rejection**: Adds cost and abstraction without solving core problem. PowerShell + vmrun provides more control and learning.

---

### Option C: Manual VM creation (Rejected)

**Approach**: Create VMs manually via VMware GUI

**Pros**:
- No scripting required
- Visual interface
- Immediate feedback

**Cons**:
- Not the DevOps way, doesn't fit our approach
- Not repeatable or version-controlled
- 30-45 minutes per cluster setup
- Human error-prone
- No IaC benefits
- Doesn't demonstrate automation skills

**Reason for rejection**: Defeats the purpose of Stage 2. Our project must demonstrate automation scenarios and capabilities.

---

### Option D: Switch to a different hypervisor (Rejected)

**Approach**: Use VirtualBox/KVM with better Terraform support

**Pros**:
- Terraform providers more mature
- Free/open-source options
- Better community support

**Cons**:
- Already invested in VMware setup (ADR-001)
- Windows 11 with TME limits hypervisor choices
- Would require re-creating template VM
- Learning VMware Workstation has production value
- Switching shows poor persistence/problem-solving

**Reason for rejection**: Sunk cost fallacy avoidance, yes, but VMware Workstation is still the right hypervisor choice (per ADR-001). Problem is Terraform provider, not hypervisor.

## Consequences

### Positive

✅ **Fast provisioning** - 3-node cluster in ~4 minutes (vs 15+ with full clones)  
✅ **Disk efficient** - 1.5GB total (vs 150GB full clones)  
✅ **Reliable** - Stable, mature tooling with 15+ years of production use  
✅ **Maintainable** - No dependency on abandoned third-party providers  
✅ **Demonstrates pragmatism** - Tool selection based on requirements, not buzzwords  
✅ **Production-relevant** - Understanding underlying APIs is valuable skill  
✅ **Idempotent operations** - Scripts support `-Force` flag for safe re-runs

### Negative

⚠️ **Not "true" IaC purist approach** - PowerShell scripts vs declarative Terraform  
⚠️ **Windows-specific** - PowerShell automation tied to Windows host  
⚠️ **Two-tool approach** - PowerShell + Ansible vs single tool  
⚠️ **Less trendy on resume** - "PowerShell automation" vs "Terraform"

### Mitigation

**Technical debt management**:
- Scripts are well-documented with inline comments
- ADRs capture decision rationale for future reference
- Could migrate to Terraform if better provider emerges
- Ansible still provides IaC for the configuration layer

**Skill development**:
- Learn Terraform in a cloud context (AWS/Azure) where providers are mature
- PowerShell skills are valuable in Windows-heavy enterprises
- Understanding vmrun teaches VMware APIs (vSphere automation)

## Implementation Evidence

**Scripts created**:
- `scripts/provision-vms.ps1` (292 lines, comprehensive automation)
- `scripts/deprovision-vms.ps1` (safety and cleanup)

**Features implemented**:
- WhatIf mode for dry-runs
- Force mode for idempotent operations
- Error handling and validation
- Timestamped logging
- Automatic Ansible inventory generation

**Provisioning metrics**:
```
Time to provision:     ~4 minutes
Time to deprovision:   ~30 seconds
Disk per VM:          ~500 MB (linked clones)
Success rate:         100% (after memory optimization)
```

## Learning Outcomes

### Technical Skills Developed

1. **Tool evaluation methodology**
   - Version testing across multiple releases
   - Community health assessment (GitHub activity)
   - Alternative research and comparison

2. **Pragmatic decision-making**
   - Requirements over ideology
   - Evidence-based tool selection
   - Documented trade-off analysis

3. **PowerShell automation**
   - VMware COM API interaction
   - Error handling and validation
   - Script parameterization (WhatIf, Force)

4. **Problem-solving persistence**
   - Tested 3 provider versions before pivoting
   - Researched root cause (abandoned project)
   - Implemented working alternative


## Future Considerations

### If Terraform Provider Improves

Monitor `elsudano/terraform-provider-vmware-workstation` repository. If:
- Snapshot support is fixed
- Regular commits resume
- Community engagement returns

**Then**: Consider migration for educational value, but only if stable.

**Migration effort**: Low (2-3 hours to convert PowerShell logic to HCL)

### For Cloud-Based Learning

When expanding homelab to cloud (AWS/Azure):
- **Use Terraform** for cloud infrastructure
- Demonstrates tool selection based on context
- Shows understanding of proper use cases

**Example**:
```
Local VMware:      PowerShell + vmrun (stable, fast)
AWS/Azure:         Terraform (mature providers)
Config management: Ansible (both environments)
```

This demonstrates **polyglot infrastructure automation** skills.

## References

- Terraform VMware Workstation provider: https://github.com/elsudano/terraform-provider-vmware-workstation
- VMware vmrun documentation: VMware Workstation Pro documentation
- PowerShell automation best practices: Microsoft Learn
- Infrastructure as Code patterns: "Infrastructure as Code" by Kief Morris

## Tags

`terraform` `powershell` `tooling-selection` `pragmatism` `automation` `troubleshooting` `ansible`
