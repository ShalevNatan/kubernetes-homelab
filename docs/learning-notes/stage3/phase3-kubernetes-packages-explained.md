# Phase 3 Deep Dive: Kubernetes Package Architecture

**Audience**: Interview preparation, deep technical understanding  
**Topics**: kubeadm vs kubelet vs kubectl, version pinning, Kubernetes APT repos

---

## The Four Packages: What They Do

### 1. kubelet (The Node Agent)

**Binary**: `/usr/bin/kubelet`  
**Config**: `/var/lib/kubelet/config.yaml` (created by kubeadm)  
**Systemd unit**: `/lib/systemd/system/kubelet.service`

**What kubelet does**:
```
API Server: "Start pod nginx-abc123 on node worker-01"
    ↓
kubelet receives pod spec via watch API
    ↓
kubelet calls containerd: "Create containers for this pod"
    ↓
containerd creates containers via runc
    ↓
kubelet monitors container health
    ↓
kubelet reports pod status back to API server
```

**Key responsibilities**:
- **Pod lifecycle management**: Start, stop, restart containers
- **Health monitoring**: Liveness/readiness probes
- **Resource enforcement**: CPU/memory limits via cgroups
- **Volume mounting**: Attach storage to containers
- **Node registration**: Tell API server "I exist, I'm ready"
- **Container runtime interface**: Talk to containerd via CRI socket

**Why it runs on EVERY node**:
- Master nodes: Runs control plane pods (kube-apiserver, etcd, etc.)
- Worker nodes: Runs application pods

**Configuration sources**:
1. **Static manifests**: `/etc/kubernetes/manifests/*.yaml` (control plane pods)
2. **API server**: Dynamic pod specs from scheduler
3. **kubelet config**: `/var/lib/kubelet/config.yaml` (node-level settings)

**Interview answer**:
> "kubelet is the node agent that runs on every Kubernetes node. It watches the API server for pod assignments, uses the container runtime (containerd via CRI) to start/stop containers, monitors pod health through probes, and reports status back to the control plane. It's the bridge between Kubernetes abstractions and actual container execution."

---

### 2. kubeadm (The Bootstrap Tool)

**Binary**: `/usr/bin/kubeadm`  
**Config**: `/etc/kubernetes/` (output, not input)

**What kubeadm does**:
```
Cluster bootstrap workflow:

Master node:
  kubeadm init
    ↓
  1. Preflight checks (swap disabled? ports available?)
  2. Generate certificates (CA, apiserver, etcd, etc.)
  3. Create static pod manifests (etcd, apiserver, controller-manager, scheduler)
  4. Start kubelet (which starts control plane pods)
  5. Upload kubeadm/kubelet ConfigMaps
  6. Create bootstrap tokens
  7. Mark master as schedulable (optional)
    ↓
  Output: kubeadm join command

Worker nodes:
  kubeadm join <master-ip>:6443 --token <token> --discovery-token-ca-cert-hash sha256:<hash>
    ↓
  1. Validate token with API server
  2. Download cluster CA certificate
  3. Create kubelet config
  4. Start kubelet
  5. Request signing of node's TLS certificate
  6. Node joins cluster
```

**Key responsibilities**:
- **Control plane setup**: Generate certs, create static manifests
- **Cluster bootstrapping**: Initial cluster creation
- **Node joining**: Add workers to cluster
- **Upgrades**: `kubeadm upgrade plan/apply` (Stage 7)
- **Certificate management**: Renew cluster certificates

**Why it's NOT a daemon**:
- Used only during cluster lifecycle events (init, join, upgrade)
- Doesn't run continuously like kubelet
- After cluster is running, kubeadm is rarely touched

**Interview answer**:
> "kubeadm is the cluster lifecycle tool. It automates the complex bootstrap process—generating certificates, creating control plane static manifests, configuring kubelet, and handling node joins. Unlike kubelet which runs continuously, kubeadm is invoked only during cluster creation, node addition, or upgrades."

---

### 3. kubectl (The CLI Client)

**Binary**: `/usr/bin/kubectl`  
**Config**: `~/.kube/config` (kubeconfig file)

**What kubectl does**:
```
User workflow:
  kubectl get pods
    ↓
  1. Read ~/.kube/config (cluster endpoint, credentials)
  2. Make HTTPS request to API server
  3. Authenticate via client certificate
  4. API server queries etcd for pod data
  5. API server returns JSON response
  6. kubectl formats output as table
    ↓
  Display: NAME  READY  STATUS  RESTARTS  AGE
```

**Key features**:
- **Declarative management**: `kubectl apply -f deployment.yaml`
- **Imperative commands**: `kubectl create deployment nginx --image=nginx`
- **Resource inspection**: `kubectl get/describe/logs/exec`
- **Cluster operations**: `kubectl drain/cordon/uncordon` (node maintenance)

**Why installed on all nodes**:
- **Master**: Troubleshooting control plane (check etcd, apiserver logs)
- **Workers**: Local debugging (check why pods aren't starting)
- **Convenience**: No need to SSH to specific node for kubectl access

**Primary usage location** (in our setup):
- **WSL2**: Main kubectl usage (after Phase 6, we'll configure kubeconfig on WSL2)
- **Nodes**: Emergency troubleshooting only

**Interview answer**:
> "kubectl is the Kubernetes CLI. It's a client-side tool that communicates with the API server over HTTPS using kubeconfig credentials. We install it on all nodes for troubleshooting flexibility, but primary usage is from operator workstations (in our case, WSL2) where we manage the cluster remotely."

---

### 4. cri-tools (CRI Debugging Utilities)

**Binary**: `/usr/bin/crictl`  
**Config**: `/etc/crictl.yaml` (optional, we use runtime-endpoint flag)

**What crictl does**:
```
Debugging workflow:
  crictl ps
    ↓
  1. Connect to containerd socket: /run/containerd/containerd.sock
  2. Call CRI gRPC method: ListContainers()
  3. containerd returns container list
  4. crictl formats output
    ↓
  Display: CONTAINER ID  IMAGE  CREATED  STATE  NAME  POD ID
```

**Key crictl commands**:
```bash
# List pods (K8s concept, not Docker concept)
crictl pods

# List containers
crictl ps

# Inspect container
crictl inspect <container-id>

# View logs
crictl logs <container-id>

# Execute command in container
crictl exec -it <container-id> /bin/sh

# Pull image
crictl pull nginx:latest

# Check runtime info
crictl info
```

**crictl vs docker CLI**:
| Command | Docker CLI | crictl |
|---------|-----------|--------|
| List containers | `docker ps` | `crictl ps` |
| View logs | `docker logs` | `crictl logs` |
| Execute command | `docker exec` | `crictl exec` |
| Pull image | `docker pull` | `crictl pull` |
| Inspect | `docker inspect` | `crictl inspect` |

**Key differences**:
- crictl shows **Kubernetes pods** (sandbox concept)
- crictl doesn't have `docker build` or `docker run` (K8s handles this)
- crictl is read-only for debugging (can't start containers manually)

**Interview answer**:
> "crictl is the CRI debugging tool from Kubernetes SIG-Node. It's like Docker CLI but for CRI runtimes—it speaks the same CRI gRPC protocol that kubelet uses to talk to containerd. We use it to troubleshoot container issues at the runtime level, below the Kubernetes abstraction layer."

---

## Kubernetes Version Pinning: Why and How

### The Problem: Version Skew

**Kubernetes version skew policy**:
```
Component compatibility matrix (K8s 1.34.3):

✅ Allowed:
  API server:  1.34.3
  kubelet:     1.34.3  (same)
  kubelet:     1.33.x  (N-1)
  kubelet:     1.32.x  (N-2)
  kubectl:     1.35.x  (N+1)
  kubectl:     1.34.3  (same)
  kubectl:     1.33.x  (N-1)

❌ NOT allowed:
  API server:  1.34.3
  kubelet:     1.31.x  (N-3, too old)
  kubelet:     1.35.x  (newer than API server)
```

**What breaks with version skew**:
- kubelet newer than API server → API calls use unknown features → rejected
- kubelet too old (N-3) → Missing required API fields → pods fail to start
- Uncontrolled upgrades → Some nodes on 1.34, some on 1.35 → unpredictable behavior

### The Solution: Package Holding

**APT package hold mechanism**:
```bash
# Install specific version
apt-get install kubelet=1.34.3-1.1

# Prevent upgrades
apt-mark hold kubelet

# Later: apt-get upgrade runs
# APT sees kubelet is held
# Skips kubelet upgrade (keeps 1.34.3-1.1)

# Deliberate upgrade (Stage 7):
apt-mark unhold kubelet
apt-get install kubelet=1.35.0-1.1
apt-mark hold kubelet
```

**Why hold all three (kubelet, kubeadm, kubectl)**:
- **kubelet**: Version skew policy (must upgrade deliberately)
- **kubeadm**: Upgrade tool must match cluster version
- **kubectl**: Optional (can be N+1), but we hold for consistency

**Why NOT hold cri-tools**:
- crictl is debugging tool, not cluster component
- Compatible with all K8s versions
- Safe to upgrade independently

**Interview answer**:
> "I pin Kubernetes package versions and use apt-mark hold because Kubernetes enforces a strict version skew policy. Uncontrolled upgrades via apt upgrade could create N-3 or newer-than-apiserver scenarios, breaking the cluster. Holding packages ensures upgrades are deliberate, following the control-plane-first, then workers upgrade pattern."

---

## Kubernetes APT Repository Structure

### Why Version-Specific Repos?

**Repository URL breakdown**:
```
https://pkgs.k8s.io/core:/stable:/v1.34/deb/
                            ^^^^^^
                            Version-specific repo
```

**What's in each repo**:
- `v1.34` repo: Only 1.34.x packages (1.34.0, 1.34.1, 1.34.2, 1.34.3, ...)
- `v1.35` repo: Only 1.35.x packages
- `v1.33` repo: Only 1.33.x packages

**Why this design**:
```
Scenario: You have v1.34 repo configured

apt-get update
apt-cache policy kubelet
# Available: 1.34.0, 1.34.1, 1.34.2, 1.34.3
# NOT available: 1.35.0 (wrong repo)

This prevents:
  apt-get upgrade  → accidentally jumps to 1.35.x ❌
```

**Upgrading to 1.35** (Stage 7):
1. Change repo from `v1.34` to `v1.35`
2. `apt-get update`
3. Now 1.35.x packages are visible
4. `apt-get install kubelet=1.35.0-1.1`

**Old repo design** (deprecated, pre-2023):
```
https://apt.kubernetes.io/
# Problem: All versions in one repo
# apt-get upgrade could jump from 1.34 → 1.35 unexpectedly
```

**New repo design** (current, 2023+):
```
https://pkgs.k8s.io/core:/stable:/v1.34/deb/
# Benefit: Version isolation, explicit upgrades
```

**Interview answer**:
> "Kubernetes moved to version-specific APT repositories in 2023. Each minor version (1.34, 1.35) has its own repo containing only that version's patches. This prevents accidental minor version jumps during apt upgrade—upgrading from 1.34 to 1.35 requires explicitly changing the repo URL, making cluster upgrades deliberate rather than accidental."

---

## kubelet Service Behavior: Why Enabled But Not Started

### The Chicken-and-Egg Problem

**kubelet requires configuration**:
```
kubelet needs:
  /var/lib/kubelet/config.yaml  ← Where is cluster? What's my name? Cgroup driver?

This file is created by:
  kubeadm init   (on master)
  kubeadm join   (on workers)

If we start kubelet now:
  systemctl start kubelet
  → kubelet crashes: "config file not found"
```

**The solution: Enable but don't start**:
```yaml
- name: Enable kubelet service
  ansible.builtin.systemd:
    name: kubelet
    enabled: yes  # ← Creates boot symlink
    # state: started  ← NOT SPECIFIED (don't start now)
```

**Service states**:
```
After Phase 3:
  systemctl is-enabled kubelet  → enabled
  systemctl is-active kubelet   → inactive

After Phase 4 (kubeadm init on master):
  systemctl is-active kubelet   → active (running)

After Phase 6 (kubeadm join on workers):
  systemctl is-active kubelet   → active (running)
```

**Why this matters**:
- kubelet will auto-start after reboot (enabled)
- But won't crash-loop now (not started without config)
- kubeadm init/join will start kubelet after creating config

**Interview answer**:
> "We enable kubelet but don't start it because kubelet requires /var/lib/kubelet/config.yaml, which doesn't exist yet. That file is created by kubeadm init on the master and kubeadm join on workers. Enabling ensures kubelet auto-starts on boot, but not starting it avoids crash-loops before cluster initialization."

---

## Package Version Format: Decoding 1.34.3-1.1

**Version string breakdown**:
```
1.34.3-1.1
^^^^^^ ^^^
  │     │
  │     └─ Debian package revision
  │        (packaging metadata changes, not K8s code)
  │
  └─ Kubernetes upstream version
     (actual K8s release)
```

**Examples**:
- `1.34.3-1.1`: K8s 1.34.3, Debian packaging revision 1.1
- `1.34.3-1.2`: Same K8s version, different packaging (e.g., systemd unit file fix)

**Why package revision matters**:
```
Scenario:
  1.34.3-1.1 released (initial packaging)
  Bug found: kubelet.service missing dependency
  1.34.3-1.2 released (fixed systemd unit)

apt-get upgrade:
  1.34.3-1.1 → 1.34.3-1.2  (safe, just packaging fix)
```

**Pinning strategy**:
```yaml
# Option 1: Pin exact package revision
name: kubelet=1.34.3-1.1
# Pro: Absolute reproducibility
# Con: Misses packaging bug fixes

# Option 2: Pin K8s version, allow package revisions
name: kubelet=1.34.3-*
# Pro: Gets packaging fixes automatically
# Con: Slightly less deterministic

# Our choice: Option 1 (exact pinning)
# Rationale: Lab environment, prefer determinism over auto-fixes
```

---

## Common Interview Questions

**Q: Why install kubectl on all nodes if we'll use it from WSL2?**
> A: Redundancy and local troubleshooting. If the master's API server is down and we need to check local kubelet logs or static pod manifests, having kubectl on the node lets us inspect the local state. It's also useful for emergency scenarios where WSL2 connectivity fails. The disk/RAM cost is negligible (~50MB), but the troubleshooting value is high.

**Q: What's the difference between kubeadm and kubelet?**
> A: kubeadm is a cluster lifecycle tool used during bootstrap, node joins, and upgrades—it's invoked manually and doesn't run continuously. kubelet is the node agent that runs as a systemd service on every node, continuously managing pod lifecycle, health monitoring, and communicating with the API server. After kubeadm initializes the cluster, it's kubelet that keeps everything running.

**Q: Can you upgrade kubelet without upgrading the API server?**
> A: No, kubelet must be the same version as the API server or up to N-2 versions older (e.g., API server 1.34, kubelet can be 1.34, 1.33, or 1.32). Upgrading kubelet to a newer version than the API server violates version skew policy and will cause API compatibility issues. Kubernetes upgrades always go control plane first (API server), then workers (kubelet).

**Q: Why doesn't crictl need version pinning?**
> A: crictl is a debugging tool, not a Kubernetes cluster component. It speaks the CRI gRPC protocol, which is stable across K8s versions. A newer crictl can talk to older containerd, and vice versa. Since it doesn't participate in the Kubernetes control plane or version skew policy, it's safe to upgrade independently.

**Q: What happens if you accidentally run kubeadm init twice?**
> A: kubeadm has safety checks. If it detects existing cluster state (/etc/kubernetes/admin.conf exists, etcd data present), it fails with "cluster already initialized" error. To re-initialize, you'd need to run `kubeadm reset` first, which cleans up all cluster state. This prevents accidentally destroying a running cluster.

---

## Summary: Interview Talking Points

**The Four Packages**:
- **kubelet**: Node agent (runs continuously, manages pods)
- **kubeadm**: Cluster lifecycle tool (bootstrap, join, upgrade)
- **kubectl**: CLI client (operator interface to API server)
- **cri-tools**: Debugging utilities (crictl for runtime inspection)

**Version Pinning**:
- Kubernetes enforces strict version skew policy (N to N-2)
- Package hold prevents accidental upgrades via apt
- Version-specific repos (v1.34, v1.35) add isolation layer

**Service State**:
- kubelet enabled but not started (needs config from kubeadm)
- Will auto-start after kubeadm init/join creates /var/lib/kubelet/config.yaml

**CRI Connectivity**:
- crictl validates containerd CRI socket is accessible
- Proves kubelet will be able to talk to container runtime

**The Big Picture**:
> "Phase 3 installs the Kubernetes control plane and node software. kubelet is the critical daemon that runs on every node, managing container lifecycle via containerd. kubeadm is used once during bootstrap to generate certificates and configure the cluster. kubectl is our operator interface. cri-tools provides low-level runtime debugging. We pin versions to prevent accidental upgrades that violate Kubernetes' version skew policy, ensuring controlled cluster upgrades in Stage 7."
