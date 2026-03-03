# Stage 3 Phase 1 Deep Dive: Why Kubernetes Needs These Kernel Settings

**Audience**: Interview preparation, deep technical understanding  
**Topics**: Kernel modules, sysctl networking, swap management

---

## Why Load `overlay` Kernel Module?

### The Problem: Container Image Storage

Containers use **layered filesystems**:
```
Container Image Layers:
┌─────────────────────────┐
│ App Layer (your code)   │  ← Read-write layer (container changes)
├─────────────────────────┤
│ Dependencies Layer      │  ← Read-only (shared across containers)
├─────────────────────────┤
│ Base OS Layer (Ubuntu)  │  ← Read-only (shared across images)
└─────────────────────────┘
```

**Challenge**: How do you efficiently store these layers?

### The Solution: OverlayFS

**OverlayFS** is a union filesystem that combines multiple layers into a single view:
```bash
# Without overlay: Each container copies entire image (wasteful)
Container 1: 500MB (full Ubuntu + app)
Container 2: 500MB (full Ubuntu + different app)
Total: 1GB

# With overlay: Layers are shared (efficient)
Base layer (Ubuntu): 200MB (shared)
Container 1 app layer: 50MB
Container 2 app layer: 50MB
Total: 300MB
```

**containerd uses overlay2 storage driver** (requires `overlay` kernel module):
- Lower layers: Read-only image layers
- Upper layer: Read-write container changes
- Merged view: What the container sees

**What breaks without it**:
- containerd fails to start
- Error: `failed to create image filesystem: overlay not supported`

**Interview answer**:
> "I loaded the overlay kernel module because containerd uses the overlay2 storage driver for efficient layered image storage. Without it, containerd can't create the union filesystem needed for container images."

---

## Why Load `br_netfilter` Kernel Module?

### The Problem: Pod Networking + iptables

Kubernetes networking involves **virtual network bridges**:
```
┌─────────────────────────────────────────────────┐
│ Node (k8s-worker-01)                            │
│                                                 │
│  ┌──────────┐      ┌──────────┐                │
│  │  Pod A   │      │  Pod B   │                │
│  │ 10.0.1.5 │      │ 10.0.1.6 │                │
│  └────┬─────┘      └────┬─────┘                │
│       │                 │                       │
│       └────────┬────────┘                       │
│                │                                │
│         ┌──────▼──────┐                         │
│         │ cni0 bridge │  ← Virtual network     │
│         │ 10.0.1.1    │     bridge (Layer 2)   │
│         └──────┬──────┘                         │
│                │                                │
│         ┌──────▼──────┐                         │
│         │    ens32    │  ← Physical interface  │
│         │192.168.70.11│                         │
│         └─────────────┘                         │
└─────────────────────────────────────────────────┘
```

**The challenge**: Traffic crosses the `cni0` bridge, but **iptables needs to see it** for:
- **Service networking**: kube-proxy uses iptables NAT rules to route traffic to service endpoints
- **Network policies**: Calico enforces firewall rules via iptables

**Default Linux behavior**: iptables **ignores** bridged traffic (only sees routed traffic)

### The Solution: br_netfilter

**br_netfilter** makes iptables aware of bridged packets:
```bash
# Without br_netfilter:
Pod A → cni0 bridge → Pod B
        ↑
        iptables can't see this traffic (bridge bypass)

# With br_netfilter:
Pod A → cni0 bridge → iptables rules → Pod B
                      ↑
                      Now visible!
```

**What breaks without it**:
- Service networking fails (can't reach ClusterIP services)
- Network policies don't work (Calico can't enforce rules)
- DNS resolution breaks (CoreDNS service unreachable)

**Interview answer**:
> "I loaded br_netfilter because Kubernetes uses iptables for service networking via kube-proxy. By default, iptables doesn't see bridged traffic, but br_netfilter exposes bridge packets to Netfilter hooks, enabling iptables rules to apply to pod-to-pod communication."

---

## Why Set `net.bridge.bridge-nf-call-iptables=1`?

### The Problem: iptables Doesn't Process Bridge Traffic by Default

Even with `br_netfilter` loaded, you need to **enable** the feature:
```bash
# Load module (makes capability available)
modprobe br_netfilter

# Enable the feature (actually use it)
sysctl -w net.bridge.bridge-nf-call-iptables=1
```

**What this sysctl does**: Tells the kernel to pass bridged IPv4 traffic through iptables chains

**iptables chains involved**:
```
Bridged packet flow WITH net.bridge.bridge-nf-call-iptables=1:

Pod A sends packet
  ↓
PREROUTING chain (iptables sees it)  ← kube-proxy NAT rules applied here
  ↓
Bridge decision (forward to Pod B)
  ↓
FORWARD chain (iptables sees it)     ← Network policy rules applied here
  ↓
POSTROUTING chain (iptables sees it)
  ↓
Pod B receives packet
```

**Without this setting**: Packets skip iptables chains entirely

**What breaks**:
- kube-proxy can't redirect service traffic (DNAT rules skipped)
- Network policies ignored (FORWARD rules skipped)
- Source NAT fails for external traffic (POSTROUTING rules skipped)

**Interview answer**:
> "Setting net.bridge.bridge-nf-call-iptables=1 ensures bridged traffic traverses iptables chains. This is critical for kube-proxy's service load balancing (DNAT rules) and Calico's network policy enforcement (FORWARD chain rules)."

---

## Why Set `net.ipv4.ip_forward=1`?

### The Problem: Inter-Node Pod Communication

Pods on different nodes need to communicate:
```
Node 1 (192.168.70.11)          Node 2 (192.168.70.12)
┌─────────────────────┐         ┌─────────────────────┐
│ Pod A (10.0.1.5)    │         │ Pod B (10.0.2.8)    │
│                     │         │                     │
│ Wants to reach ──────────────────→ 10.0.2.8        │
│ 10.0.2.8            │         │                     │
└─────────────────────┘         └─────────────────────┘
```

**Packet flow**:
1. Pod A sends packet to 10.0.2.8
2. Node 1's routing table says "send to Node 2 via 192.168.70.12"
3. Kernel needs to **forward** the packet from `cni0` interface to `ens32` interface
4. Node 2 receives packet, forwards to Pod B

**Default Linux behavior**: IP forwarding is **disabled** (security default for desktop systems)

### The Solution: Enable IP Forwarding
```bash
sysctl -w net.ipv4.ip_forward=1
```

**What this does**: Allows the kernel to forward packets between network interfaces

**What breaks without it**:
- Pod-to-pod communication across nodes fails
- Pods can only talk to other pods on the same node
- Cross-node services don't work

**Interview answer**:
> "Enabling net.ipv4.ip_forward allows the kernel to route packets between network interfaces. In Kubernetes, this is essential for cross-node pod communication—packets need to be forwarded from the pod network interface (cni0) to the physical interface (ens32) to reach pods on other nodes."

---

## Why Disable Swap?

### The Problem: Memory Guarantees

Kubernetes uses **resource requests and limits** for memory:
```yaml
# Pod specification
resources:
  requests:
    memory: "256Mi"  # Guaranteed minimum
  limits:
    memory: "512Mi"  # Maximum allowed
```

**Kubernetes assumption**: Pods get **dedicated physical RAM** (no swap)

**Why swap breaks this**:
- Pod requests 256Mi RAM
- kubelet schedules it on a node with 256Mi free
- OS starts swapping pod's memory to disk (slow)
- **Pod performance degrades unpredictably** (disk I/O vs RAM speed)

### Kubernetes Design Decision: No Swap

From Kubernetes sig-node:
> "Swap makes performance unpredictable. We want consistent, deterministic behavior."

**Historical context**:
- Pre-1.8: kubelet didn't check for swap (pods could swap, causing issues)
- 1.8+: kubelet **refuses to start** if swap is detected (preflight check)
- 1.28+: Swap support added as **alpha feature** (off by default, requires explicit config)

**What breaks with swap enabled**:
```
kubelet preflight check:
[ERROR Swap]: running with swap on is not supported. Please disable swap
```

**Interview answer**:
> "Kubernetes disables swap because it breaks memory resource guarantees. If a pod with 256Mi request gets swapped to disk, its performance becomes unpredictable—memory access that should be nanoseconds (RAM) becomes milliseconds (disk). kubelet's preflight checks enforce this by refusing to start if swap is active."

---

## Persistent vs Runtime Configuration

### Why Two Steps?
```bash
# Step 1: Runtime (lost on reboot)
modprobe overlay
sysctl -w net.ipv4.ip_forward=1

# Step 2: Persistent (survives reboot)
echo "overlay" > /etc/modules-load.d/k8s.conf
echo "net.ipv4.ip_forward = 1" > /etc/sysctl.d/k8s.conf
```

**Runtime configuration**: Applied to running kernel immediately  
**Persistent configuration**: Files read by systemd on boot

**Why both?**:
- Runtime: Makes changes effective **now** (don't want to reboot just to test)
- Persistent: Ensures changes survive reboot (production requirement)

**systemd boot process**:
1. `systemd-modules-load.service` reads `/etc/modules-load.d/*.conf`
2. Loads listed modules (`overlay`, `br_netfilter`)
3. `systemd-sysctl.service` reads `/etc/sysctl.d/*.conf`
4. Applies kernel parameters

**Interview answer**:
> "I applied settings both to the running kernel and to persistent config files. The runtime changes (modprobe, sysctl -w) let me continue immediately without rebooting. The persistent files (/etc/modules-load.d/, /etc/sysctl.d/) ensure settings survive reboots—systemd reads these on boot."

---

## Common Interview Questions

**Q: Why does Kubernetes care about iptables?**
> A: kube-proxy uses iptables for service load balancing. When you access a ClusterIP service, iptables DNAT rules redirect traffic to backend pod IPs. CNI plugins like Calico also use iptables for network policy enforcement.

**Q: What's the difference between overlay and overlay2?**
> A: overlay2 is the modern version of the overlay storage driver. It's more efficient (fewer inodes, better performance) and is the default for Docker/containerd. "overlay" (v1) is deprecated. Both require the `overlay` kernel module.

**Q: Can Kubernetes run with swap enabled?**
> A: As of 1.28, there's alpha support for swap with strict configuration (LimitedSwap, UnlimitedSwap modes). But it's off by default—production clusters disable swap to ensure predictable memory performance. In this lab, we follow the standard practice: disable swap entirely.

**Q: What happens if br_netfilter isn't loaded?**
> A: CNI plugins will install successfully, but pod networking will be broken. Pods won't be able to reach services (kube-proxy's iptables rules are skipped). You'll see symptoms like "dial tcp 10.96.0.1:443: i/o timeout" when pods try to reach the Kubernetes API service.

---

## Summary: Interview Talking Points

**Kernel Modules**:
- `overlay`: Enables containerd's layered image storage
- `br_netfilter`: Makes iptables aware of bridge traffic

**sysctl Settings**:
- `net.bridge.bridge-nf-call-iptables=1`: Process bridge traffic through iptables (service networking)
- `net.ipv4.ip_forward=1`: Allow packet forwarding between interfaces (cross-node communication)

**Swap**:
- Disabled to ensure predictable memory performance (Kubernetes design decision)
- kubelet refuses to start if swap is active

**The Big Picture**:
> "These settings prepare the node's kernel for Kubernetes networking. Kubernetes doesn't just run containers—it creates a virtual network where pods can communicate across nodes, services load-balance traffic via iptables, and network policies enforce security. The kernel needs specific capabilities enabled to support this."
