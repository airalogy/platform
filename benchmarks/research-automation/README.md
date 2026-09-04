# Research automation acceptance benchmarks

This directory defines the stable, machine-readable acceptance scenarios for Airalogy Platform research automation. Run them from the repository root with:

```bash
pnpm research:benchmarks
```

The suite verifies platform behavior, governance, provenance, and failure boundaries. It does not claim that a real wet-lab experiment succeeded, that an instrument is safe merely because software tests passed, or that scientific findings are valid without domain review and real Evidence.

Each scenario is intentionally cross-cutting:

- **CNT human-in-the-loop** checks the AIRA-to-Protocol-to-Record iteration boundary.
- **Fermentation multi-source integration** checks typed result integration and human-finalized Result Packages.
- **Protein-purification method evolution** checks reviewed Knowledge, validated Evidence, Protocol-improvement review, and exact version lineage.
- **OT-2 governed control** checks bounded physical sequencing, interlocks, fresh high-risk review, and deterministic pause behavior.

The executable tests live in `apps/api/tests/test_research_acceptance_benchmarks.py`. The JSON scenario IDs, checkpoints, and prohibited shortcuts are part of the acceptance contract and should change only when the product boundary changes deliberately.
