# ADR-008: Container Runtime Selection

**Status**: Approved  
**Date**: 2026-02-07  
**Deciders**: Shalev  
**Stage**: 3 (Kubernetes Bootstrap)  
**Supersedes**: None  
**Related**: ADR-009 (CNI Plugin), ADR-010 (Kubernetes Version)

---

## Context

Kubernetes requires a container runtime that implements the Container Runtime Interface (CRI) specification. The runtime is responsible for:
- Pulling container images from registries
- Managing container lifecycle (create, start, stop, delete)
- Executing containers with proper isolation (namespaces, cgroups)
- Providing logs and metrics to kubelet

**Historical Context**: Docker was the original Kubernetes runtime, but was deprecated in K8s 1.20 (Dec 2020) due to its non-CRI architecture requiring the `dockershim` compatibility layer. As of K8s 1.24 (May 2022), dockershim was completely removed, forcing all clusters to use CRI-native runtimes.

**Current Landscape (Feb 2026)**:
- **containerd**: Most widely adopted (87% of production clusters - CNCF Survey 2024)
- **CRI-O**: RedHat/OpenShift ecosystem preference (~10% market share)
- **Others**: Docker (via cri-dockerd shim), Kata Containers (specialized security use cases)

---

## Decision Drivers

### Technical Requirements
- **CRI compliance**: Must implement CRI v1 specification natively
- **Kubernetes compatibility**: Proven stability with K8s 1.34.3
- **OCI compliance**: Support for OCI image and runtime specifications
- **Systemd integration**: Proper cgroup management on Ubuntu 24.04

### Operational Requirements
- **Troubleshooting tooling**: CLI tools for debugging (`crictl`, runtime-specific tools)
- **Documentation quality**: Comprehensive guides for common issues
- **Community support**: Active forums, GitHub issues, Stack Overflow coverage

### Learning Objectives
- **Production applicability**: Skills transferable to real-world environments
- **Debugging depth**: Understanding container internals, not just abstraction layers

---
## Decision

**I chose containerd as the container runtime.**

### Rationale

**Primary reasoning**:
1. **Industry Standard Alignment**: 87% production adoption means troubleshooting knowledge is widely applicable. When issues arise (and they will), Stack Overflow, GitHub issues, and community forums will have relevant solutions.

2. **Interview Credibility**: containerd is expected baseline knowledge for senior DevOps roles. Demonstrating deep understanding of containerd architecture, troubleshooting, and integration with kubelet shows mainstream competency.

3. **Cloud Provider Consistency**: All major managed K8s services (GKE, EKS, AKS) use containerd. Skills learned in this homelab transfer directly to production cloud environments.

4. **Operational Maturity**: 8+ years of production hardening means fewer edge cases, better systemd integration, and more predictable behavior.

5. **Learning Depth**: containerd's architecture (daemon → shim → runc) provides excellent teaching material for understanding container fundamentals without unnecessary complexity.

**Why NOT CRI-O**:
- CRI-O's benefits (pure OCI compliance, lightweight design) don't outweigh the practical challenges of smaller community support and less comprehensive documentation
- For a learning/portfolio project, mainstream technology choice demonstrates engineering judgment (prefer proven solutions over niche alternatives)
- The portfolio value of "I used CRI-O" is lower than "I deeply understand containerd, which 87% of production clusters use"

**Trade-off Acceptance**:
- We accept that containerd includes some Docker-compatibility features that aren't strictly necessary for K8s
- This trade-off is worthwhile for the operational benefits (better docs, more community support, cloud provider alignment)

---


- [CNCF containerd Project](https://containerd.io/)
- [Kubernetes CRI Documentation](https://kubernetes.io/docs/concepts/architecture/cri/)
- [CNCF Survey 2024: Container Runtime Adoption](https://www.cncf.io/reports/cncf-annual-survey-2024/)
- [Google Kubernetes Engine: containerd Migration](https://cloud.google.com/kubernetes-engine/docs/concepts/using-containerd)
- [AWS EKS: containerd Runtime](https://docs.aws.amazon.com/eks/latest/userguide/dockershim-deprecation.html)
- [containerd vs CRI-O Comparison (2024)](https://kubernetes.io/blog/2024/01/container-runtime-comparison/)
