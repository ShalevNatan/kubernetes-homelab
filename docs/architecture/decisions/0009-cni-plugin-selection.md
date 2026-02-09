# ADR-009: CNI Plugin Selection

**Status**: Approved  
**Date**: 2026-02-07  
**Decider**: Shalev  
**Stage**: Kubernetes Bootstrap

## Context
Kubernetes needs a CNI plugin to enable pod networking. Without it, pods can’t communicate and core components (like CoreDNS) won’t run.  
This cluster is a **3-node homelab** running on **VMware Workstation (NAT)**. The goal isn’t scale — it’s learning networking properly, including policies and troubleshooting, in a setup that still resembles real-world clusters.

## Decision Drivers
- Works reliably with Kubernetes 1.34 on Ubuntu 24.04
- Compatible with VMware NAT (no external routing or BGP required)
- Strong NetworkPolicy support
- Good tooling for debugging and visibility
- Skills should transfer to production Kubernetes, not just labs

## Options Considered

### Calico
A full-featured CNI with strong NetworkPolicy support. Can run in overlay mode (IP-in-IP / VXLAN) without BGP, which fits a NAT-based homelab well. Mature, well-documented, and widely used in production.

### Flannel
Simple and lightweight, but does not support NetworkPolicies on its own. Fine for basic connectivity, but limited from a learning and security perspective.

### Cilium
Modern eBPF-based CNI with advanced features and observability. Powerful, but adds complexity and kernel-level concerns that don’t fit the current stage of the lab.

## Decision
**Calico is selected as the CNI plugin.**

## Rationale
I chose Calico because it hits the right balance between depth and practicality.  
Network policies matter. Calico lets me work hands-on with Kubernetes’ security model (ingress/egress rules, namespace isolation), which Flannel can’t provide.  
Production relevance. Calico is widely used in real clusters (including EKS for policy enforcement), so the time spent learning it carries over.  
Good debugging experience. Tools like `calicoctl` make networking behavior visible instead of opaque.  
Right level of complexity. More meaningful than Flannel, but without diving into eBPF internals like Cilium.  
Cilium is intentionally deferred to a later stage once the fundamentals are solid.

## Consequences

### Positive
- Full NetworkPolicy support from day one
- Better understanding of pod networking internals
- No need to swap CNIs later for security-focused stages
- Experience aligns with production Kubernetes environments

### Negative
- Higher resource usage than Flannel
- Slightly more setup and configuration complexity

These trade-offs are acceptable for a homelab focused on learning, not minimal footprint.

## Implementation Notes
- **Install method**: Calico Operator
- **Pod CIDR**: `192.168.0.0/16` (no conflict with VMware NAT `192.168.70.0/24`)
- **Encapsulation**: IP-in-IP
