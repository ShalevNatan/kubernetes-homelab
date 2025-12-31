# 3. Network Architecture - VMnet8 NAT Single-NIC Design

**Date:** 2025-12-31  
**Status:** Accepted  
**Deciders:** Shalev Natan  
**Tags:** #infrastructure #networking #vmware #foundation

---

## Context and Problem Statement

The Kubernetes cluster requires reliable networking for node communication, internet access (package updates, container image pulls), and external access to services (via LoadBalancer). We need to design a network architecture that works within VMware Workstation Pro's capabilities and Windows host constraints.

**Background:**
- Hypervisor: VMware Workstation Pro in WHP mode
- Host OS: Windows 11 Pro (with networking limitations)
- Cluster: 3 VM nodes requiring inter-node communication
- Requirements:
  - Static IP addressing (no DHCP)
  - Internet access for all nodes
  - Isolated from home network (192.168.1.x)
  - Support for MetalLB LoadBalancer (192.168.70.200-250)
  - Simple, reliable configuration

**Key constraint:** Windows networking features are limited or broken on this system:
- `New-NetNat` (PowerShell NAT) is non-functional (WMI corruption from Hyper-V WHP coexistence)
- `netsh routing` unavailable (Windows Server feature only)
- Internet Connection Sharing (ICS) locks subnet to 192.168.137.0/24 (inflexible)

---

## Decision Drivers

- **Reliability:** Network must be stable and not dependent on broken Windows features
- **Simplicity:** Minimize configuration complexity for rapid lab iteration
- **Internet access:** All nodes need outbound connectivity (apt, Docker Hub, GitHub)
- **Static IPs:** Kubernetes requires stable node identities
- **Isolation:** Cluster should be isolated from home network for security and cleanliness
- **MetalLB support:** Need IP range for LoadBalancer service allocation
- **Time to value:** Prefer working solution over architecturally ideal but fragile setup

---

## Considered Options

1. **VMnet8 (Default NAT) with single NIC per VM**
2. **Custom Windows NetNat with VMnet (host-only) + dual NICs**
3. **VMnet1 (Host-only) + VMnet8 (NAT) dual-NIC architecture**
4. **Bridged networking (VMnet0) with home network DHCP**

---

## Decision Outcome

**Chosen option:** "VMnet8 (Default NAT) with single NIC per VM"

**Network configuration:**
- Subnet: 192.168.70.0/24
- Gateway: 192.168.70.1 (Windows host via vmnetnat.exe)
- NAT provider: VMware's built-in NAT service
- DHCP: Disabled (static IPs only)

**IP allocation:**
```
192.168.70.1       - Windows host (gateway)
192.168.70.10      - k8s-master-01
192.168.70.11      - k8s-worker-01
192.168.70.12      - k8s-worker-02
192.168.70.13      - k8s-worker-03 (optional 4th node)
192.168.70.200-250 - MetalLB LoadBalancer pool
```

**Justification:**

VMnet8 is VMware's default NAT network and works immediately without any Windows configuration. After attempting to create a custom NetNat configuration (which failed due to WMI corruption from Hyper-V), the pragmatic choice was to use VMware's proven NAT implementation.

The single-NIC design trades the architectural ideal of management/data plane separation for operational simplicity and reliability. In a learning environment where experiments fail and VMs get rebuilt frequently, having one stable network that "just works" is more valuable than complex multi-NIC setups that introduce failure points.

---

## Consequences

### Positive Outcomes

- ✅ **Zero configuration:** VMnet8 works out-of-box, no Windows networking setup required
- ✅ **Proven reliability:** VMware's NAT has 20+ years of maturity
- ✅ **Immediate internet access:** All nodes can reach package repos, container registries
- ✅ **Isolated from home network:** Cluster traffic doesn't leak to 192.168.1.x
- ✅ **Simple troubleshooting:** One network, one routing table, one gateway
- ✅ **MetalLB compatible:** LoadBalancer IPs in same subnet as nodes (works without additional routing)

### Negative Outcomes

- ⚠️ **No management/data separation:** All traffic (SSH, kubectl, pod-to-pod) shares one network
- ⚠️ **Single point of failure:** If VMnet8 fails, entire cluster loses connectivity
- ⚠️ **NAT performance overhead:** Slight latency vs bridged networking (negligible for lab)
- ⚠️ **Non-routable from home network:** Can't access cluster services from other devices without port forwarding

### Neutral Outcomes

- ℹ️ **Different from production:** Enterprise clusters typically have separate management/data/storage networks
- ℹ️ **VMware dependency:** Network tied to VMware's NAT service (not portable to other hypervisors)
- ℹ️ **Fixed subnet:** 192.168.70.0/24 is set unless VMnet8 is reconfigured

---

## Detailed Analysis of Options

### Option 1: VMnet8 (Default NAT) Single-NIC ✅ SELECTED

**Description:**
Use VMware's pre-configured NAT network (VMnet8) with static IP assignments. Each VM has one network adapter connected to VMnet8.

**Why accepted:**
- Works immediately after VMware installation
- No dependency on broken Windows networking features
- VMware's NAT service (vmnetnat.exe) handles routing reliably
- Single failure domain to troubleshoot
- Sufficient for learning Kubernetes networking concepts (CNI, Services, Ingress)

**Trade-offs accepted:**
- No network segmentation (management + data on same NIC)
- Slightly less realistic compared to production multi-NIC designs
- Trade-off justified: Reliability and simplicity over architectural purity

---

### Option 2: Custom Windows NetNat + VMnet (Host-only) + Dual NICs

**Description:**
Create a custom NAT using PowerShell `New-NetNat` with a host-only VMware network, then add second NIC (VMnet8) for internet access.

**Why rejected:**
- **`New-NetNat` is broken on this system** (WMI corruption from Hyper-V/WHP)
- Attempted implementation failed with error:
```
  New-NetNat : Instance creation failed
  WMI provider returned error 0x80041001
```
- Diagnosing and fixing WMI would require risky system repairs
- Even if fixable, introduces fragile dependency on Windows networking stack
- Dual-NIC adds complexity without clear benefit for lab use case

**Trade-off rejected:**
- Theoretical benefit (network segmentation) not worth unstable foundation

---

### Option 3: VMnet1 (Host-only) + VMnet8 (NAT) Dual-NIC Architecture

**Description:**
Configure each VM with two NICs:
- NIC 1 (VMnet1): Management network for SSH, kubectl (192.168.100.0/24)
- NIC 2 (VMnet8): Data/internet network for pod traffic (192.168.200.0/24)

**Why rejected:**
- Added operational complexity (two routing tables per node)
- Risk of routing conflicts (which interface for pod traffic?)
- Requires careful kernel routing configuration (`ip route` rules)
- No functional benefit for lab learning objectives
- Harder to troubleshoot when experiments fail
- VMnet1 doesn't provide internet access (would still need VMnet8 for apt/docker)

**Trade-off rejected:**
- Production-like architecture doesn't justify doubled troubleshooting complexity
- Better to learn Kubernetes concepts on simple, stable network first

---

### Option 4: Bridged Networking (VMnet0) with Home Network DHCP

**Description:**
Connect VMs directly to home network (192.168.1.x) via bridged adapter, using router DHCP for IP allocation.

**Why rejected:**
- **DHCP breaks Kubernetes:** Node hostnames/IPs must be static
- Exposes cluster to home network (security concern, traffic pollution)
- VMs visible to other devices (potential conflicts, accidental access)
- Home router may not support MetalLB IP range reservation
- Less portable (different subnet if moving to different location)

**Trade-off rejected:**
- Convenience of home network access not worth Kubernetes instability and security exposure

---

## Network Design Details

### VMnet8 Configuration

**VMware Virtual Network Editor settings:**
```
Network: VMnet8 (NAT)
Subnet: 192.168.70.0
Subnet mask: 255.255.255.0 (/24)
Gateway: 192.168.70.1 (automatic, provided by VMware)
DHCP: Disabled (unchecked)
NAT settings: Default (vmnetnat.exe handles translation)
```

**Why this subnet:**
- 192.168.70.0/24 chosen to avoid common home network ranges:
  - 192.168.1.0/24 (most routers)
  - 192.168.0.0/24 (some routers)
  - 10.0.0.0/8 (corporate VPNs)
- VMware default is 192.168.xxx.0/24, we selected .70 for uniqueness
- /24 provides 254 usable addresses (more than sufficient for lab)

---

### Static IP Assignment Strategy

**Why static IPs are mandatory:**
- Kubernetes nodes register with API server using hostname + IP
- DHCP lease changes would break cluster membership
- etcd clustering requires stable peer IPs
- kubectl config references node IPs directly

**IP allocation scheme:**
```
.1          - Gateway (reserved by VMware)
.2-.9       - Reserved for future infrastructure (DNS, NTP, etc.)
.10-.19     - Kubernetes control plane nodes
.20-.99     - Kubernetes worker nodes
.100-.199   - Reserved for future expansion
.200-.250   - MetalLB LoadBalancer IP pool
.251-.254   - Reserved
```

---

### MetalLB Integration

**LoadBalancer IP pool:** 192.168.70.200-250

**Why this range:**
- High enough to avoid node IPs (.10-.99)
- Provides 51 IPs for LoadBalancer services
- Allows ~50 concurrent exposed services (more than sufficient for lab)
- Same subnet as nodes (no routing required)

**Access from host:**
- Services with LoadBalancer IPs are accessible from Windows host
- Example: Grafana at 192.168.70.200:3000 reachable from browser
- No port forwarding or SSH tunneling required for basic access

---

## Implementation Notes

**VMware configuration performed:**
1. Opened Virtual Network Editor (as Administrator)
2. Selected VMnet8
3. Disabled DHCP
4. Verified subnet: 192.168.70.0/24
5. No additional changes needed (NAT works by default)

**Per-VM network configuration (Ubuntu):**
```yaml
# /etc/netplan/00-installer-config.yaml example (master node)
network:
  version: 2
  ethernets:
    ens33:  # VMware default NIC name
      addresses:
        - 192.168.70.10/24
      routes:
        - to: default
          via: 192.168.70.1
      nameservers:
        addresses:
          - 8.8.8.8
          - 8.8.4.4
```

**Validation:**
```bash
# From any VM node
ping 192.168.70.1        # Gateway reachable
ping 8.8.8.8             # Internet reachable
curl google.com          # DNS + HTTP working
```

**Timeline:** Implemented December 2025 (Stage 1)

**Dependencies:**
- ADR-0001 (Hypervisor selection - VMware Workstation)

---

## Validation Criteria

**Success indicators:**

- [x] All VM nodes can ping each other (inter-node communication works)
- [x] All VM nodes can reach internet (apt updates, docker pulls successful)
- [x] Gateway (192.168.70.1) reachable from all nodes
- [x] No IP conflicts or routing errors
- [ ] MetalLB assigns LoadBalancer IPs successfully (validate in Stage 4)
- [ ] Services accessible from Windows host via LoadBalancer IPs (validate in Stage 4)
- [ ] CNI plugin establishes pod network without conflicts (validate in Stage 3)

**When to revisit this decision:**

- If network performance becomes bottleneck (unlikely in NAT)
- If need to access cluster from other devices on home network (would require port forwarding setup)
- If multi-NIC architecture becomes requirement for advanced networking experiments
- If migrating to different hypervisor or bare metal

---

## Future Considerations

**Potential enhancements (not currently needed):**

1. **Port forwarding from host:**
   - Forward specific ports (e.g., 80→192.168.70.200:80) for external access
   - Allows home network devices to reach cluster services

2. **Secondary network for storage:**
   - Add VMnet2 (host-only) for dedicated storage traffic
   - Useful if implementing Ceph or distributed storage (Stage 7+)

3. **VPN access:**
   - Set up WireGuard or OpenVPN on one node
   - Allow remote access to cluster from outside home network

**Current single-NIC NAT design is sufficient for Stages 1-6.**

---

## Lessons Learned So Far

**What worked well:**
- Attempting custom NetNat first revealed system constraints early
- Pragmatic fallback to VMnet8 saved hours of troubleshooting
- Static IP planning upfront prevents future subnet exhaustion

**What could be improved:**
- Could have tested Windows networking features before designing architecture
- Documentation of WMI corruption issue may help others in similar situations

---

## References

- VMware Workstation networking documentation
- Kubernetes networking requirements: https://kubernetes.io/docs/concepts/cluster-administration/networking/
- MetalLB configuration: https://metallb.universe.tf/
- Related decisions:
  - [ADR-0001: Hypervisor Selection](0001-hypervisor-selection.md)
  - [ADR-0002: Memory Allocation Strategy](0002-memory-allocation-strategy.md)

---

_This network design prioritizes reliability and operational simplicity over architectural complexity, reflecting the pragmatic constraints of a Windows-hosted home lab environment._
