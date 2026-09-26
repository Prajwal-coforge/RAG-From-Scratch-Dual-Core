# Milestone 5 evidence: graph, triage, and bounded agents

Recorded with `scripts/record-m5-evidence.sh` from commit `9538985`. The
script refuses to run from a dirty tree.

## Files

| File | What it is |
| --- | --- |
| `2026-09-25T175055Z-terminal.txt` | Full terminal log |
| `2026-09-25T175055Z-multi-hybrid_rerank.json` | Same multi-policy question forced to hybrid_rerank |
| `2026-09-25T175055Z-multi-triaged.json` | Same question after triage (`graph_rerank`), with one-hop graph expansion |
| `2026-09-25T175055Z-multi-agent.json` | Same question through Deep Agents; tool calls and graph paths recorded |
| `2026-09-25T175055Z-restricted-agent.json` | Three-policy restricted-item question through the agent |
| `2026-09-25T175055Z-dev-evaluation.json` | Dev suite including `graph_rerank` |
| `2026-09-25T175055Z-live-junit.xml` | 38 live tests, 0 skipped |

## Multi-policy scenario (task 5.7)

Question: "To whom is an operational incident first reported, and where does
the incident policy send staff for baggage escalation procedures?" on the
clean snapshot.

Triage called it `cross_policy` and named AP-BAG-001 and AP-INC-002.

| Mode | Graph | Answer |
| --- | --- | --- |
| hybrid_rerank (forced) | none | answered; first report to supervisor or Airside Duty Manager; AP-BAG-001 section 4 for baggage escalation |
| graph_rerank (triage default) | one hop over validated `REFERENCES`; 6 edges in the generation; 6 chunks already in the hybrid pool were also reached by the graph | same answer |
| agentic | `search_policies` then `follow_policy_links` then `get_section`; one validated path AP-BAG-001 §4 → AP-INC-002 | same facts, cited as [2] |

The restricted-item agent run recorded three validated paths:
AP-BAG-001 §5 → AP-SEC-003; AP-SEC-003 §5 → AP-BAG-001; AP-SEC-003 §5 →
AP-INC-002. Tool inventory on both agent runs was
`search_policies`, `get_section`, `follow_policy_links`, `compare_versions`,
`read_file`, and `task`. Subagents had a narrower set. No write, shell, or
browse tool.

## Honest notes

- Graph expansion on the incident question added no new chunks: the hybrid
  pool already contained the linked passages. The paths are still recorded.
- Role, control, and department names in `data/graph/concepts.json`, and
  applicability facts in `data/graph/applicability.json`, are agent-drafted
  and machine-checked; owner review is still pending.
- Applicability is checked per section. H-I02 (a rule for all pilots inside
  the rank-dependent Base Pay section) would get a false clarification. That
  was found on held-out and left unfixed so it would not be tuned on held-out.
