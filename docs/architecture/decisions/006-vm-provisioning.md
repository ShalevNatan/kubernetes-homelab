# ADR-006: VM Memory Allocation Strategy

**Status**: Accepted  
**Date**: 2026-01-10  
**Decision Makers**: Shalev  
**Related**: ADR-002 (Memory Allocation Planning)

## Context

During initial VM provisioning in Stage 2.2, attempted to allocate 16GB RAM to all three VMs (total 48GB). VMware Workstation failed to start the third VM with error:
```
Error: The operation was canceled
Suggested: Reduce memory 
```

Host system specifications:
- Total RAM: 64GB
- Free RAM at provision time: ~16GB
- OS: Windows 11 Pro with VMware Workstation Pro 25H2

The host has sufficient total RAM, but VMware could not allocate the full requested amount due to:
1. Host OS memory requirements
2. VMware overhead
3. Other running processes
4. Memory fragmentation

## Decision

memory allocation optimized for actual Kubernetes component requirements:

- **Master node (k8s-master-01)**: 16GB RAM
- **Worker nodes (k8s-worker-01, k8s-worker-02)**: 12GB RAM each

**Total allocation**: 40GB (16 + 12 + 12)  
**Host buffer**: ~24GB for OS stability

## Rationale

### Component Memory Requirements Analysis

**Control Plane (Master Node) - Justification for 16GB:**
```
etcd:                      ~500 MB  (cluster state database)
kube-apiserver:            ~200 MB  (API endpoint)
kube-controller-manager:   ~100 MB  (reconciliation loops)
kube-scheduler:            ~50 MB   (pod placement)
CoreDNS:                   ~20 MB   (cluster DNS)
Container runtime:         ~200 MB  (containerd)
System overhead:           ~300 MB  (OS + monitoring)
────────────────────────────────────
Kubernetes overhead:       ~1.4 GB
Available for workloads:   ~14.6 GB  ✓ Sufficient
```

**Worker Nodes - Justification for 12GB:**
```
kubelet:                   ~100 MB  (node agent)
kube-proxy:                ~30 MB   (network proxy)
Container runtime:         ~200 MB  (containerd)
System overhead:           ~300 MB  (OS + monitoring)
────────────────────────────────────
Kubernetes overhead:       ~630 MB
Available for pods:        ~11.4 GB  ✓ More than sufficient
```

### Design Principles Applied

1. **Right-sizing over maximum allocation**
   - Allocate based on measured requirements, not theoretical maximums
   - Avoids resource waste and host instability

2. **Symmetric worker configuration**
   - Both workers identical (12GB each)
   - Predictable scheduling behavior
   - Simplified troubleshooting

3. **Master differentiation**
   - Control plane has higher memory needs than workers
   - etcd can grow with cluster size
   - API server handles all cluster requests

4. **Host system stability**
   - 24GB buffer prevents host swapping
   - Maintains responsive Windows environment
   - Room for VMware overhead and other tools

### Production Realism

Real-world Kubernetes deployments often use:
- **Cloud instances**: t3.medium (4GB), t3.large (8GB), t3.xlarge (16GB)
- **On-prem workers**: 8-16GB is common for non-intensive workloads
- **Control plane**: Often 8-16GB depending on cluster size

My configuration (16GB master, 12GB workers) represents a realistic mid-size cluster setup.

## Alternatives Considered

### Option A: 16GB for all nodes (Rejected)
```
Configuration: 16 + 16 + 16 = 48GB
Status: FAILED during provisioning
```

### Option B: Master 12GB, Workers 16GB (Rejected)
```
Configuration: 12 + 16 + 16 = 44GB
Status: Theoretical (not tested)
```

**Pros:**
- Symmetric workers
- Maximum worker capacity

**Cons:**
- Inverted priority (workers get more than control plane)
- May still hit allocation limits
- Master constrains cluster scalability

**Reason for rejection**: Control plane usually has slightly higher memory requirements than workers; this configuration inverts the priority incorrectly.

---


## Consequences

### Positive

✅ **Stable provisioning** - All VMs start successfully within host constraints  
✅ **Sufficient capacity** - 11.4GB available per worker for pod workloads  
✅ **Symmetric workers** - Predictable scheduling, easier troubleshooting  
✅ **Host stability** - 24GB buffer prevents swapping and maintains responsiveness  
✅ **Production-realistic** - Memory allocation mirrors real-world cluster sizing  
✅ **Demonstrates optimization thinking** - Portfolio evidence of resource management skills

### Negative

⚠️ **Worker capacity limits** - Cannot run pods requiring >10GB memory per pod  
⚠️ **Total pod capacity** - Must be mindful of aggregate memory requests across workers  
⚠️ **Future workload constraints** - Very memory-intensive applications may require reconfiguration

### Mitigation Strategies

If memory-intensive workloads are needed in later stages:

1. **Reduce cluster size, increase allocation**
   - Option: 2-node cluster (1 master, 1 worker @ 24GB)
   - Maintains total 40GB allocation

2. **Strict pod resource limits**
   - Implement ResourceQuotas
   - Define LimitRanges
   - Practice production-grade resource governance

3. **Workload optimization**
   - Use memory-efficient alternatives (e.g., Loki instead of Elasticsearch)
   - Implement horizontal scaling (more small pods vs. fewer large pods)

4. **Conceptual autoscaling**
   - Document how you would scale in production
   - Demonstrate understanding even if not implemented

## Validation

### Provisioning Success
```
Phase 1: Cloning VMs from template snapshot
✓ k8s-master-01: 4 vCPU, 16384MB RAM
✓ k8s-worker-01: 4 vCPU, 12288MB RAM  
✓ k8s-worker-02: 4 vCPU, 12288MB RAM

Phase 2: Starting VMs
✓ All VMs started successfully

Phase 3: Network Initialization  
✓ All VMs acquired DHCP IPs
```

### Memory Verification (via `free -h` on workers)
```
Worker-01:
  Total: 11Gi (12GB allocated - ~1GB kernel reserved)
  Used:  512Mi
  Free:  11Gi  ✓ Excellent headroom

Worker-02:
  Total: 11Gi
  Used:  536Mi  
  Free:  11Gi  ✓ Excellent headroom
```

**Note**: VMs report 11GiB instead of 12GB due to:
- Binary (GiB) vs decimal (GB) unit differences
- Linux kernel reserved memory (~400-500MB for kernel, drivers, buffers)
- This is expected and normal behavior

### Resource Allocation Summary
```
Total host RAM:        64 GB
Allocated to VMs:      40 GB (62.5%)
Host buffer:           24 GB (37.5%)
Status:                ✓ Healthy margin for stability
```

## Implementation Notes

Memory allocation configured in `scripts/provision-vms.ps1`:
```powershell
$vms = @(
    @{
        Name = "k8s-master-01"
        CPU = 4
        RAM = 16384  # 16GB - Control plane
        PlannedIP = "192.168.70.10"
        Role = "master"
    },
    @{
        Name = "k8s-worker-01"
        CPU = 4
        RAM = 12288  # 12GB - Worker nodes
        PlannedIP = "192.168.70.11"
        Role = "worker"
    },
    @{
        Name = "k8s-worker-02"
        CPU = 4
        RAM = 12288  # 12GB - Worker nodes
        PlannedIP = "192.168.70.12"
        Role = "worker"
    }
)
```

## References

- Kubernetes production requirements: https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/#before-you-begin
- etcd hardware recommendations: https://etcd.io/docs/v3.5/op-guide/hardware/
- VMware Workstation memory management documentation
- ADR-003: Initial memory allocation planning (Stage 1)

## Tags

`infrastructure` `resource-optimization` `vmware` `memory-allocation` `constraints`
