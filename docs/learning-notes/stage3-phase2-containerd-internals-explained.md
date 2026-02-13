# Phase 2 Deep Dive: containerd Architecture & Configuration

**Audience**: Interview preparation, deep technical understanding  
**Topics**: Container runtime architecture, CRI, cgroup drivers, systemd integration

---

## Why containerd (Not Docker)?

### Historical Context: The Docker Deprecation

**Timeline**:
- **Pre-2016**: Docker was the only runtime for Kubernetes
- **2016**: Kubernetes introduced CRI (Container Runtime Interface) spec
- **2017**: containerd extracted from Docker as standalone project
- **2020**: Kubernetes 1.20 deprecated Dockershim (compatibility layer for Docker)
- **2022**: Kubernetes 1.24 removed Dockershim entirely
- **2024-present**: containerd is the standard (87% adoption)

**Why the change?**

Docker's architecture was too complex for Kubernetes:
```
Kubernetes using Docker (deprecated):
kubelet → dockershim → Docker daemon → containerd → runc → container
          ↑ Kubernetes-maintained compatibility layer (technical debt)

Kubernetes using containerd (current):
kubelet → containerd → runc → container
          ↑ Direct CRI communication (cleaner, faster)
```

**Key insight**: Docker adds unnecessary layers. containerd is what Kubernetes actually needed all along.

---

## containerd Architecture: How Containers Actually Run

### The Component Stack
```
┌─────────────────────────────────────────────────────────┐
│ Kubernetes Control Plane                                │
│ (kubelet decides "start pod X with container Y")        │
└──────────────────┬──────────────────────────────────────┘
                   │
                   │ CRI gRPC calls
                   │ (RunPodSandbox, CreateContainer, StartContainer)
                   ▼
┌─────────────────────────────────────────────────────────┐
│ containerd (daemon)                                     │
│ - Listens on /run/containerd/containerd.sock           │
│ - Implements CRI gRPC server                           │
│ - Manages image pulling, storage, container lifecycle  │
└──────────────────┬──────────────────────────────────────┘
                   │
                   │ Spawns containerd-shim processes
                   │ (one per container, outlives containerd restarts)
                   ▼
┌─────────────────────────────────────────────────────────┐
│ containerd-shim                                         │
│ - Proxy between containerd and runc                    │
│ - Collects container exit status                       │
│ - Forwards stdin/stdout/stderr                         │
│ - Survives containerd restarts (container keeps running)│
└──────────────────┬──────────────────────────────────────┘
                   │
                   │ Calls runc (OCI runtime)
                   ▼
┌─────────────────────────────────────────────────────────┐
│ runc                                                    │
│ - Creates Linux namespaces (PID, NET, MNT, UTS, IPC)   │
│ - Sets up cgroups (resource limits)                    │
│ - Configures network interfaces (veth pairs)           │
│ - Executes container process                           │
│ - Exits after container starts (ephemeral)             │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Container Process                                       │
│ - Runs in isolated namespaces                          │
│ - Resource-limited by cgroups                          │
│ - Sees root filesystem from overlay mount              │
└─────────────────────────────────────────────────────────┘
```

### Key Components Explained

**1. containerd (daemon)**
- **Binary**: `/usr/bin/containerd`
- **Socket**: `/run/containerd/containerd.sock` (CRI gRPC endpoint)
- **Config**: `/etc/containerd/config.toml`
- **Responsibilities**:
  - Image management (pull, push, list, delete)
  - Container lifecycle (create, start, stop, delete)
  - Network namespace setup
  - Storage management (overlay filesystem)

**2. containerd-shim**
- **Binary**: `/usr/bin/containerd-shim-runc-v2`
- **Purpose**: Decouples container from containerd daemon
- **Why it exists**:
```
  Problem: If containerd crashes, all containers die (unacceptable)
  Solution: containerd-shim stays running, keeps container alive
```
- **Process tree**:
```
  containerd (PID 1234)
    └─ containerd-shim (PID 5678) ← Survives containerd restarts
         └─ nginx (PID 5679) ← Actual container process
```

**3. runc**
- **Binary**: `/usr/bin/runc`
- **Purpose**: OCI-compliant low-level container runtime
- **What it does**:
  - Creates Linux namespaces (isolation)
  - Configures cgroups (resource limits)
  - Sets up root filesystem (overlay mount)
  - Executes container's entrypoint
  - **Exits immediately** after container starts (ephemeral)
