# ADR-010: Kubernetes Version Pinning Strategy

**Status**: Approved  
**Date**: 2026-02-07  
**Decider**: Shalev  
**Stage**: Kubernetes Bootstrap

## Context
Kubernetes releases frequent minor versions with a limited support window. Choosing a version for this homelab means balancing stability, support lifetime, and the ability to learn and document upgrades without unnecessary risk.

This lab starts in **Feb 2026** and is expected to run until **Oct 2026**. The chosen version must remain supported throughout that period and behave predictably over time.

## Decision Drivers
- Supported through the full lab timeline
- Mature enough to avoid early-adopter issues
- Compatible with containerd and Calico
- Commonly seen in real-world clusters
- Explicit version pinning for reproducibility

## Options Considered

### Kubernetes 1.34.x
Mid-lifecycle release with several patch versions already available. Actively supported by cloud providers and widely deployed in production.

### Kubernetes 1.35.x
Latest stable release. Longer support window, but still early in its lifecycle with less real-world feedback and documentation.

### Kubernetes 1.33.x
Very mature, but close to end-of-life, which would force an upgrade mid-project.

### Auto-updating to latest patch
Reduces maintenance effort but breaks reproducibility and makes documentation harder to keep accurate.

## Decision
**Kubernetes 1.34.3 is selected and explicitly pinned.**

## Rationale
I chose 1.34.3 because it sits in a solid maturity window: stable, well-documented, and still modern. It remains supported for the entire lab duration and closely reflects what’s commonly run in production environments.

Pinning the exact patch version keeps the lab reproducible and avoids unexpected behavior from automatic updates. The fact that 1.34 approaches EOL near the end of the project is intentional — it creates a natural opportunity to practice and document a controlled upgrade later on.

## Consequences

### Positive
- Stable and predictable cluster behavior
- Full support coverage for the lab timeline
- Clear upgrade path without urgency
- Documentation remains accurate over time

### Negative
- Not running the absolute latest version
- Upgrade will be required later (planned, not disruptive)

## Implementation Notes
- **Pinned version**: Kubernetes `1.34.3`
- **Upgrade strategy**: Manual, deliberate upgrade in a later stage
- **Package holds**: Enabled to prevent accidental updates
