# 5. Reproducibility and determinism

Reproducibility is treated here as an enforced property of the system rather than a description of good practice, because it is the property that makes the validation claim auditable.

**Seeded inference.** All permutation tests use seeded pseudo-random number generation, and pseudo *p*-values are computed as (M+1)/(R+1) rather than M/R, so a *p*-value of exactly zero is not reportable and the discreteness of the null distribution is respected.

**Pinned data.** Geometry and both real variables are pinned snapshots with SHA-256 checksums recorded in a manifest, so a re-run refers to the same inputs rather than to whatever a remote service currently serves.

**Machine-readable traces.** Each run emits a JSON trace recording every proposal, every gate's diagnostics and decision, every prescription, and the resulting revision. Figure 7 reproduces a fragment. The trace is the audit surface for the provenance invariant of Section 3.2: an examiner can verify that each numeric constant in the executed code traces to a gate computation or an audited template default.

**Byte-identical gate verdicts.** Re-running the deterministic pipeline reproduces the gate verdict files byte for byte.

This last claim requires a scope statement, and we state it rather than leaving it to be discovered. The pipeline writes four trace files. The two recording gate decisions, diagnostics, and prescriptions are byte-identical across runs. The two recording retrieval and sandbox execution are **not**: they embed wall-clock timing fields, which vary by construction. Timing is physically non-deterministic; the decisions are what the determinism claim concerns. Accordingly we claim byte-identical *gate verdicts*, never byte-identical *traces* — the broader phrasing would be true only under a careful reading and false under the natural test of comparing every file.

**Test suite.** The implementation carries 236 passing tests, with 33 skipped where a live network, Docker, or gVisor dependency is unavailable in the executing environment. Every gate branch has an explicit test. We deliberately do not report a coverage percentage: no coverage tool has been run, and quoting a number we have not measured would be precisely the class of unfalsifiable claim this architecture exists to prevent.
