# 2. Memory Allocation Strategy - 48GB Reserved for VMs

**Date:** 2025-12-31  
**Status:** Accepted  
**Deciders:** Shalev Natan  
**Tags:** #infrastructure #memory #resource-planning #foundation

---

## Context and Problem Statement

The home lab runs on a Windows 11 Pro host with 64GB total RAM. We need to determine how much memory to allocate to VMs while maintaining host system stability and responsiveness.

**Background:**
- Total system RAM: 64GB DDR4
- Host OS: Windows 11 Pro (with VBS/Hyper-V overhead)
- Hypervisor: VMware Workstation Pro in WHP mode
- Target: 3-node Kubernetes cluster (1 control plane + 2 workers)
- Use case: Production-grade K8s learning environment with monitoring stack

**Key constraint:** Host reserve must prevent Windows memory pressure under full VM load, ensuring lab usability and safe experimentation. Without adequate reserve, memory paging would destabilize kubelets, interrupt long-running tests, and create unpredictable learning conditions.

---

## Decision Drivers

- **Host stability:** Windows needs sufficient RAM to avoid memory pressure and swap activity
- **VM node performance:** Kubernetes nodes require adequate memory for kubelet, pods, system services
- **Cluster capability:** Must support observability stack (Prometheus, Grafana, Loki)
- **Future flexibility:** Leave headroom for potential 4th worker node
- **WHP overhead:** Hyper-V layer consumes additional baseline memory (measured: ~2-3GB)
- **Kubernetes minimums:** Control plane needs more RAM than workers
- **Operational reliability:** Avoid memory overcommit to prevent host paging and VM instability

---

## Considered Options

1. **48GB for VMs, 16GB for host (3 VM nodes × 16GB each)**
2. **56GB for VMs, 8GB for host (4 VM nodes × 14GB each)**
3. **40GB for VMs, 24GB for host (3 VM nodes: 16GB + 2×12GB)**
4. **32GB for VMs, 32GB for host (3 VM nodes: 12GB + 2×10GB)**

---

## Decision Outcome

**Chosen option:** "48GB reserved for VMs, 16GB for Windows host"

**Cluster configuration:**
- k8s-master-01: 16GB RAM
- k8s-worker-01: 16GB RAM
- k8s-worker-02: 16GB RAM
- Total VM allocation: 48GB
- Host reserve: 16GB

**Justification:**

This allocation provides a balanced approach between VM node capability and host stability. Each Kubernetes node receives 16GB—sufficient for kubelet, system pods, and application workloads including a full observability stack. 

The 16GB host reserve accounts for empirically measured usage:
- Windows 11 baseline + VBS/Hyper-V: ~7GB (measured at idle)
- VMware Workstation Pro overhead: ~2-3GB (measured with 3 VMs running)
- Active applications (browser, VS Code, terminals): ~3-5GB
- Safety buffer: ~1-2GB

This leaves breathing room to prevent memory pressure without wasting available RAM.

**Memory commitment approach:**

VMware setting "Fit all VM memory into reserved RAM" is enabled, which locks 48GB upfront rather than allowing dynamic overcommit. This decision explicitly trades flexibility for stability—overcommit would risk host paging under load, potentially destabilizing kubelets and interrupting experiments. For a learning environment where repeatability matters, guaranteed memory allocation is essential.

---

## Consequences

### Positive Outcomes

- ✅ **Adequate VM node resources:** 16GB per node supports Kubernetes + monitoring stack comfortably
- ✅ **Host stability:** 16GB reserve prevents Windows memory pressure and swap thrashing (validated empirically)
- ✅ **Uniform node sizing:** Identical RAM across all nodes simplifies capacity planning
- ✅ **Headroom for expansion:** Can potentially add 4th node (12GB) if needed without reconfiguration
- ✅ **Professional sizing:** 16GB matches common cloud instance types (t3.xlarge, Standard_D4s_v3)
- ✅ **Predictable performance:** No overcommit means no surprise slowdowns during experiments

### Negative Outcomes

- ⚠️ **No 4th full-sized node:** Can't run 4×16GB VM nodes simultaneously without reducing host reserve
- ⚠️ **Memory committed upfront:** VMware locks 48GB immediately, no dynamic allocation
- ⚠️ **Limited burst capacity:** Can't temporarily overcommit for short-term testing
- ⚠️ **No room for large databases:** Won't support memory-intensive apps like Elasticsearch at scale

### Neutral Outcomes

- ℹ️ **Fixed cluster size:** 3-node cluster is set unless we reconfigure memory allocation
- ℹ️ **Different from production:** Real clusters often use smaller nodes (8GB) with horizontal scaling
- ℹ️ **Monitoring overhead:** Prometheus/Grafana will consume ~4-6GB across cluster (acceptable)

---

## Detailed Analysis of Options

### Option 1: 48GB for VMs, 16GB for Host ✅ SELECTED

**Configuration:**
- 3 VM nodes × 16GB = 48GB total
- Host reserve: 16GB
- VMware setting: "Fit all VM memory into reserved RAM" enabled

**Why accepted:**
- Sweet spot between VM node capability and host usability
- 16GB per node is industry-standard sizing for dev/test Kubernetes
- Host has comfortable headroom (tested: Windows uses ~10-12GB with VMs running)
- Matches recommended Kubernetes control plane minimum (8GB) with 2× safety margin
- Workers have room for DaemonSets + multiple application pods
- No memory overcommit eliminates risk of host paging and kubelet instability

**Key validation:**
- Tested host memory usage with all 3 VM nodes running: 52-54GB used, 10-12GB free
- No Windows memory warnings during normal operation
- VMware UI remains responsive under load

---

### Option 2: 56GB for VMs, 8GB for Host

**Configuration:**
- 4 VM nodes × 14GB = 56GB total
- Host reserve: 8GB

**Why rejected:**
- 8GB host reserve is insufficient for Windows 11 + WHP overhead + applications
- Measured: Windows alone uses 6-8GB baseline in WHP mode
- Leaves only 0-2GB for VMware UI, browser, code editor
- High risk of memory pressure and system slowdown
- 14GB per VM node is awkward sizing (not aligned with common instance types)

**Trade-off rejected:**
- Gaining 4th node not worth sacrificing host stability
- Better to run 3 healthy nodes than 4 struggling nodes with an unstable host

---

### Option 3: 40GB for VMs, 24GB for Host

**Configuration:**
- 1 master × 16GB + 2 workers × 12GB = 40GB total
- Host reserve: 24GB

**Why rejected:**
- 24GB host reserve is excessive (over-provisioning)
- Asymmetric worker sizing (16GB vs 12GB) complicates capacity planning
- Workers at 12GB limits observability stack deployment flexibility
- Unused host RAM provides no benefit (not accessible to VM nodes)

**Trade-off rejected:**
- Wasting 8GB of RAM that could improve VM node capabilities
- Asymmetric sizing creates operational complexity for minimal gain

---

### Option 4: 32GB for VMs, 32GB for Host

**Configuration:**
- 1 master × 12GB + 2 workers × 10GB = 32GB total
- Host reserve: 32GB (split evenly)

**Why rejected:**
- 12GB control plane is tight for etcd + API server + scheduler + controller manager
- 10GB workers struggle with monitoring stack (Prometheus node exporter, Promtail, etc.)
- Over-provisioning host RAM that won't be utilized
- Insufficient for Stage 5 observability goals (Prometheus requires aggregation capacity)

**Trade-off rejected:**
- Sacrificing cluster capability for unused host memory
- Would require careful pod resource limits, reducing learning flexibility

---

## Memory Breakdown per VM Node

### Control Plane Node (k8s-master-01: 16GB)

**Estimated usage:**
```
Kubernetes system components:
├─ kubelet, kube-proxy:        ~500MB
├─ etcd:                       ~1-2GB (depends on cluster size)
├─ kube-apiserver:             ~1-2GB
├─ kube-controller-manager:    ~500MB
├─ kube-scheduler:             ~500MB
├─ CoreDNS (2 replicas):       ~200MB
├─ CNI plugin (Calico/Cilium): ~500MB
└─ Total Kubernetes:           ~4-6GB

Ubuntu OS baseline:             ~1GB
Buffer for spikes:              ~2-3GB
Remaining for workloads:        ~6-8GB
```

**Headroom:** Sufficient for control plane + light workloads

---

### Worker Nodes (k8s-worker-01/02: 16GB each)

**Estimated usage:**
```
Kubernetes system components:
├─ kubelet, kube-proxy:        ~500MB
├─ CNI plugin:                 ~300MB
├─ Monitoring DaemonSets:      ~800MB (node-exporter, promtail)
└─ Total system:               ~1.6GB

Ubuntu OS baseline:             ~1GB
Buffer for stability:           ~1-2GB
Available for application pods: ~12-13GB per worker
```

**Headroom:** Comfortable for Prometheus, Grafana, Loki, demo applications

---

## Implementation Notes

**VMware Configuration:**
1. Global memory reservation: 48GB
2. Memory allocation mode: "Fit all VM memory into reserved RAM"
   - **Why this matters:** Prevents memory overcommit that would cause host paging
   - **Trade-off:** Memory locked upfront vs dynamic allocation flexibility
   - **Decision rationale:** Stability and predictability over theoretical efficiency
3. Individual VM settings: 16384MB (16GB) per VM node

**Validation performed:**
```powershell
# Host memory check (PowerShell)
Get-WmiObject Win32_OperatingSystem | 
  Select-Object TotalVisibleMemorySize, FreePhysicalMemory

# Measured result: ~10-12GB free with all VM nodes running
# Windows Task Manager confirmation: No memory pressure warnings
```

**Timeline:** Implemented December 2025 (Stage 1)

**Dependencies:** 
- ADR-0001 (Hypervisor selection - VMware in WHP mode)

---

## Validation Criteria

**Success indicators:**

- [x] Host remains responsive with all 3 VM nodes running (verified)
- [x] No Windows memory warnings during normal operation (verified)
- [x] VMware UI performance acceptable (verified)
- [ ] Kubernetes control plane stable under observability load (validate in Stage 5)
- [ ] Workers handle Prometheus + Grafana + Loki without OOM kills (validate in Stage 5)
- [ ] Can run realistic application workloads (validate in Stage 6+)

**When to revisit this decision:**

- If Stage 5 observability stack causes OOM errors on workers
- If application workloads require more than 12GB combined capacity per worker
- If Windows host shows memory pressure (sustained >90% usage)
- If upgrading to 128GB RAM becomes feasible

---

## Future Considerations

**Potential adjustments:**

1. **If control plane is oversized:**
   - Consider reducing master to 12GB
   - Reallocate 4GB to workers (14GB total each)

2. **If host needs more:**
   - Reduce each VM node to 14GB (42GB total)
   - Increase host reserve to 22GB

**Current allocation provides best balance for Stage 1-6 goals.**

---

## References

- Kubernetes official hardware requirements: https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/
- VMware Workstation memory management documentation
- Related decisions:
  - [ADR-0001: Hypervisor Selection](0001-hypervisor-selection.md)
  - [ADR-0003: Network Architecture](0003-network-architecture.md)

---

## Lessons Learned

_(To be filled in after Stage 8 completion)_

**What went well:**
- 

**What could be improved:**
- 

**Would we make the same decision again?**
- 

---

_This allocation reflects a pragmatic balance between cluster capability and host system stability for an 8-month learning journey, and provides flexibility for workload expansion, observability experiments, and potential 4th worker addition._
