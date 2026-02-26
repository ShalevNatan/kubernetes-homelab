# ADR-0011: Lab Control Dashboard

**Date:** 2026-02-26  
**Status:** Accepted  
**Deciders:** Shalev  
**Related ADRs:** ADR-0005 (Infrastructure Automation Tooling), ADR-0006 (VM Provisioning), ADR-0007 (Ansible Execution Environment)

---

## Context

As the homelab automation matured through Stages 1–3, the infrastructure became fully automated via PowerShell (VM lifecycle) and Ansible (node configuration, Kubernetes bootstrap). However, a new class of friction emerged that automation alone does not solve: **workflow orchestration and operational visibility**.

### The Problem

The end-to-end process from "no VMs exist" to "Kubernetes cluster ready for workloads" involves multiple sequential steps across different tools and environments:

```
Edit config (Notepad++) → provision-vms.ps1 → Ansible playbook(s) → verify cluster
         ↑                                                                  |
         └─────────── deprovision-vms.ps1 ←── manual decision ────────────┘
```

Pain points observed in practice:

1. **No single control point** — the operator mentally tracks state and manually sequences steps across PowerShell, WSL2, and text editors
2. **High context-switching cost** — changing a VM spec requires opening a script in a text editor, finding the right variable, editing, saving, then running the script
3. **No real-time feedback** — stdout from long-running Ansible playbooks is only visible if you're watching the terminal; there's no persistent log or status
4. **Fragile sequencing** — nothing prevents running a playbook against VMs that aren't yet provisioned, or provisioning when VMs already exist
5. **Cognitive overhead compounds over time** — as more playbooks are added (CNI, ingress, storage, monitoring), the mental model of "what do I run next" becomes a liability

This is not a performance problem. Individual playbook execution time is acceptable. The problem is **workflow friction and lack of observability over the full lifecycle pipeline**.

### Why This Matters for the Portfolio

In production environments, platform teams build internal developer platforms (IDPs) and operational dashboards precisely to solve this class of problem. Tools like Rancher, vCenter, and ArgoCD exist because raw CLI automation, while necessary, is insufficient as an operational interface. Building a control plane for this homelab demonstrates understanding of that principle — not just "I can write Ansible" but "I understand why you need a layer above Ansible."

---

## Decision

Build a **local web-based Lab Control Dashboard** that serves as the single operational interface for the homelab lifecycle.

### Architecture

```
┌─────────────────────────────────────────────────┐
│              Browser (localhost:8000)            │
│           HTML + JS Frontend                    │
│  VM Cards | Playbook Runner | Config Editor     │
└────────────────────┬────────────────────────────┘
                     │ HTTP + WebSocket
┌────────────────────▼────────────────────────────┐
│           FastAPI Backend (Python)              │
│                                                 │
│  /api/vms        → vmrun.exe calls             │
│  /api/playbooks  → ansible-playbook (WSL2)     │
│  /api/provision  → provision-vms.ps1           │
│  /api/config     → read/write config files     │
│  /ws/logs        → WebSocket log streaming     │
└─────────────────────────────────────────────────┘
```

The backend runs on Windows, calls PowerShell scripts natively, and invokes Ansible via WSL2 subprocess. Real-time log streaming is implemented via WebSockets, piping subprocess stdout directly to the browser as execution happens.

### Repository Location

```
tools/
└── lab-dashboard/
    ├── backend/
    │   ├── main.py
    │   ├── routers/
    │   └── requirements.txt
    ├── frontend/
    │   └── index.html
    └── README.md
```

---

## Alternatives Considered

### Option A: Enhanced PowerShell Script with Menu UI
A terminal-based menu sequencing existing scripts.

**Pros:** No new technology, stays entirely in PowerShell  
**Cons:** No real-time streaming without complex job handling, no config editing UX, terminal-only, not portfolio-differentiated

**Rejected because:** Solves sequencing but not observability or config editing. Adds no portfolio value beyond what already exists.

### Option B: Electron Desktop App
A proper desktop application wrapping a Node.js backend.

**Pros:** Native desktop feel, installable  
**Cons:** Heavy, slow to build, overkill for a single-user local tool, packaging complexity adds no learning value

**Rejected because:** Cost/benefit ratio is poor. A local web app is functionally identical for this use case with a fraction of the complexity.

### Option C: Python CLI with Rich TUI
A terminal UI using the `textual` or `rich` Python library.

**Pros:** Stays in terminal, looks impressive, no browser dependency  
**Cons:** Harder to do config editing with forms, less intuitive for at-a-glance VM state visibility

**Not selected as primary.** May be revisited as a companion CLI for headless use in a later stage.

### Option D: FastAPI + Web Frontend (Selected)
**Pros:**
- Browser-native — no installation, works immediately
- WebSockets for real-time log streaming are well-supported
- FastAPI is industry-standard for internal tooling APIs
- Frontend can be iterated independently of the backend
- Python backend has full access to Windows subprocess, filesystem, and WSL2
- Genuinely portfolio-worthy: demonstrates understanding of platform tooling patterns

**Cons:**
- Requires Python on the Windows host
- Two moving parts (backend + frontend) vs a single script
- Backend process must be running before the UI is accessible

---

## Management Plane Placement

The dashboard runs **external to the Kubernetes cluster**, on the Windows host.

This follows the same pattern used in production by every major infrastructure management tool (vCenter, Rancher, ArgoCD, Lens). The rationale is simple: a management plane that depends on the thing it manages is an operational anti-pattern. The dashboard must exist before the cluster is provisioned and must survive while the cluster is being torn down or rebuilt. Cluster status visibility is implemented via `kubectl` calls from the host — it does not require in-cluster deployment.

---

## Consequences

### Positive
- Single entry point for all lab operations
- Real-time log streaming makes long Ansible runs observable and debuggable
- Config editing via forms eliminates the text editor workflow
- Pattern can grow with the lab — Stage 5 observability links, Stage 6 ArgoCD shortcuts, etc.
- Demonstrates platform engineering thinking in portfolio and interviews

### Risks
- Adds Python as a dependency on the Windows host
- The dashboard itself must be started before use — not zero-friction
- Could become its own maintenance burden if over-engineered early

### Mitigations
- Keep the backend thin: it orchestrates existing scripts, it does not replace them
- Scripts must remain runnable standalone — the dashboard is never a hard dependency
- Version the dashboard in Git alongside the rest of the lab
- Accept that v1 will be rough; the Git history showing evolution is part of the portfolio value

---

## Notes

The spec for this tool is intentionally not fully defined upfront. The feature set will be discovered iteratively through the build process. This ADR captures the architectural direction; implementation details will be reflected in commit history and `tools/lab-dashboard/README.md`.
