# Setup & Technical Decisions

This document captures **stabilized technical decisions** that shape the system’s development approach.

## Modular Development Strategy

To address multiple high-impact technical risks simultaneously, the team adopted a **modular development strategy**, enabling parallel workstreams focused on:

- Document extraction research
- Matching algorithm refinement
- User interface and functional controls (subsequent phase)

This approach reduces schedule risk while preserving integration discipline.

---

## Extraction Approach Constraints

Initial extraction tools were deemed insufficient for handling complex, graphics-layer PDF resumes.

As a result:
- Research shifted toward more robust document processing techniques
- Library selection is evaluated based on layout handling, not simple text parsing
- Compatibility with the existing Python-based pipeline remains a core constraint

---

## Infrastructure & Execution Constraints

All live execution and testing must remain compatible with:
- A Unix-based (Linux) server environment
- Secure, VPN-restricted access
- Institution-managed infrastructure

These constraints inform both library selection and system architecture decisions.
