# Disha AI — Host Hardware Discovery (HARDWARE.md)

> **Historical host snapshot:** Hardware and benchmark observations are machine/date-specific and do not describe the current runtime unless rechecked. See [Deployment](../DEPLOYMENT.md) for the scope of current host checks.


**Generated:** 2026-11-07  
**Host Environment:** Apple Silicon macOS Workstation

---

## 1. Hardware Specifications

| Component | Measured Specification | Architectural Implication |
|---|---|---|
| **Operating System** | macOS 27.2 (Darwin arm64) | Full UNIX socket, `launchd`, Metal, and POSIX signal support |
| **Processor (CPU)** | Apple M5 (Mac17,3) | 10 logical cores with ultra-high memory bandwidth |
| **Unified Memory (RAM)** | 16.00 GB LPDDR5X | Sufficient headroom for simultaneous execution of PostgreSQL, Docker, Laya (322M/421M), local Whisper, and 7B/8B local LLMs (Q4_K_M) |
| **GPU / Neural Engine** | Apple Silicon GPU + 16-core Neural Engine | PyTorch MPS (`device='mps'`), Apple MLX, and CoreML hardware acceleration supported natively |
| **Available Disk Storage** | 269.58 GB free / 460.38 GB total | Ample space for local model weights, Docker images, and database WAL logs |
| **Python Runtimes** | Python 3.12.13 (Venv) / Python 3.15.0 (System) | Project executes strictly in `.venv` (Python 3.12.13 with `uv`) |

---

## 2. Hardware Recommendations for Phase 2 & Phase 6

1. **Laya Execution:**
   - **Recommended Device:** Apple Silicon MPS (`torch.device("mps")`) or tuned multi-thread CPU (`torch.set_num_threads(4)`).
   - In-process inference latency benchmarked at **~98ms P50**, well within the 650ms internal turn budget.
2. **Local STT Execution:**
   - `faster-whisper` (base or small model) runs in `<180ms` on Apple Silicon via CoreML / MPS, offering an alternative to Groq Whisper when offline.
3. **Local LLM Execution:**
   - For complete offline local execution, MLX / llama.cpp running `Qwen2.5-7B-Instruct` or `Llama-3.1-8B-Instruct` fits within 4.5 GB RAM at 45-60 tokens/sec.
4. **Cloudflare Tunnel Deployment:**
   - Apple M5 host has persistent low-power standby and can run `cloudflared` as a persistent `launchd` service with automatic restarts and zero port forwarding.
