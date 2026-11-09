# Disha AI — Security Policy & Vulnerability Disclosure

## 1. Security Overview

Disha AI is an open-source, edge-grounded clinical companion and conversational health coaching platform. Because Disha AI processes sensitive patient dialogue and physiological indicators, security, patient data isolation, and clinical safety are paramount.

For detailed architecture diagrams, threat models, and privacy invariants, consult [docs/SECURITY.md](docs/SECURITY.md) and [docs/security/key-rotation.md](docs/security/key-rotation.md).

---

## 2. Supported Versions

We provide security patches, vulnerability fixes, and invariant hardening for the following releases:

| Version | Supported | Critical Clinical Bugfixes | Security Patches |
|:---|:---:|:---:|:---:|
| `1.0.x` / `main` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `< 1.0.0` | :x: | :x: | :x: |

---

## 3. Reporting a Vulnerability

**DO NOT report suspected security vulnerabilities through public GitHub issues or discussions.**

If you discover a security vulnerability, clinical safety circumvention, PHI exposure, or credential leak, please report it via one of the following private channels:

1. **GitHub Private Vulnerability Reporting**: Open a private advisory under the repository's **Security > Advisories** tab.
2. **Dedicated Security Inbox**: Email `security@disha.ai` (or primary maintainer at `sahil.sp.sp.2003@gmail.com`).

### What to Include

Please provide as much information as possible to help us triage and remediate the issue rapidly:

- **Type of Issue**: e.g., Patient isolation breach, prompt injection bypass, secret leakage, denial of service, unhandled PHI in telemetry.
- **Affected Components**: e.g., `disha_core/voice.py`, `disha_core/pipeline/breaker.py`, `disha_core/routers/chat.py`.
- **Reproduction Steps**: Step-by-step instructions or minimal reproduction scripts/curl commands.
- **Proof of Concept**: Synthetic non-PHI test payload demonstrating the unexpected behavior.
- **Impact Assessment**: Description of potential attack vectors or clinical implications.

---

## 4. Response Timelines & SLAs

Our security response strike team adheres to the following response commitments:

| Severity | Initial Triage & Acknowledgement | Remediation & Patch SLA | Public Disclosure Coordination |
|:---|:---:|:---:|:---:|
| **Critical** (PHI leak, Patient isolation failure, Emergency bypass) | < 12 Hours | < 24 Hours | 30 Days (coordinated) |
| **High** (DoS, Token replay, Authentication bypass) | < 24 Hours | < 72 Hours | 45 Days |
| **Medium** (Rate limit degradation, Non-critical disclosure) | < 48 Hours | < 7 Days | 60 Days |
| **Low** (Info disclosure without exploit, Code hygiene) | < 5 Days | Next Minor Release | N/A |

---

## 5. Security & Invariant Guarantees

Every pull request and merge must satisfy automated verification gates:

- **Zero Hardcoded Secrets**: Scanned continuously via `gitleaks` and `scripts/hardcode-check`.
- **Multi-Tenant Patient Isolation**: Patient identifiers are strictly derived from cryptographic bearer token digests; direct client-provided `patient_id` payloads are rejected.
- **Deterministic Emergency Breaker**: Immediate routing to 112 emergency deflection (<0.02ms) executed ahead of any LLM token generation.
- **Zero-PHI Telemetry**: Instant regex scrubbing for Aadhaar numbers, phone numbers, MRN/UHID, and personal identifiers before logging or queuing into Merkle audit ledgers.
- **Immutable Audit Chain**: Append-only local SQLite WAL linked into a SHA-256 cryptographic audit chain.

---

## 6. Key Rotation & Incident Protocol

In the event of key compromise or infrastructure rotation, follow the formal playbook in [docs/security/key-rotation.md](docs/security/key-rotation.md):
- Invalidate revoked keys within 15 minutes across Groq, Gemini, Cloudflare, and database endpoints.
- Re-run `scripts/repo-check` and `make test` to verify stack resilience.
