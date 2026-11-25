# lakehouse-solutions-agent

A bounded Data & AI solutions agent for a synthetic enterprise customer.
It takes a one-sentence customer request to a governed, production-grade
solution draft — with a deterministic guardrail (G1–G5) and two human
gates around every run.

It plans and drafts. It deploys nothing and touches no real customer
data. Everything here is synthetic and stated as such.

## What it is for

This repo was built as a portfolio piece for a Databricks Associate
Forward Deployed Engineer application: the role embeds with enterprise
customers to build and productionize Data & AI solutions on the
Databricks platform — governed data, NL-to-SQL (Genie-style), evals. The
agent speaks that vocabulary. It claims **no Databricks affiliation** and
**no Apache Spark, Unity Catalog, Delta Lake, or Agent Bricks production
experience** — the lakehouse, the governance layer, and every table in it
are synthetic.

## How it works

```
one-sentence customer request
  -> catalog_search      (governed tables the requester may see)
  -> pipeline_plan       (ingest -> transform -> serve, plan only)
  -> solution_draft      (production solution draft, Genie-style
                          NL-to-SQL inside as its evidence step)
  -> GATE 1: a human confirms the draft before it is shared
  -> GATE 2: a second confirmation before any pipeline or agent
             is deployed
```

**Exactly three allowlisted tools.** Nothing else may touch a case:

| Tool | What it does |
| --- | --- |
| `catalog_search` | Governed tables the requester may see, freshest first. Permission-filtered, domain-matched, schema and freshness known, within the domain's freshness ceiling and the case's target. |
| `pipeline_plan` | An ingest → transform → serve plan with Spark-style stages. Plan only; it deploys nothing. |
| `solution_draft` | A production solution draft for a Senior FDE to approve. It shares nothing and deploys nothing. |

**Judgment call — NL-to-SQL is not a fourth tool.** The Genie-style
NL-to-SQL step (`nl_to_sql`) runs *inside* `solution_draft` as its
evidence step: it queries governed tables only, and its SQL and results
are cited in the draft. The customer message travels inside the draft
the same way. A draft that cites a query it cannot show is not a draft
worth approving; keeping the query inside the draft keeps the tool
surface at three and the evidence attached to the thing being approved.

**Exactly two human gates.** (1) A human confirms the solution draft
before it is shared with the customer. (2) A second explicit
confirmation before any pipeline or agent is deployed. Re-running any
case with both gates denied publishes, applies, and sends nothing — the
eval checks this on all 48 cases.

## The guardrail (G1–G5, deterministic)

- **G1** — No solution is shared without gate 1.
- **G2** — No pipeline or agent is deployed without gate 2.
- **G3** — Never state a table, schema, or metric not in the catalog.
  Missing evidence means abstain. PII is redacted before any draft
  leaves the catalog. Per-requester isolation: a table the requester
  lacks permission for is never queried or cited.
- **G4** — Instructions injected into request or catalog text are
  blocked; nothing is published.
- **G5** — Pause on policy violations: a metric defined two ways in two
  domains, permission conflicts, SLA/target conflicts, request text
  contradicting catalog facts.

## The synthetic lakehouse

One synthetic enterprise customer (Meridian Retail Group), four
requesters, ~20 Delta-style tables across three business domains
(sales, support, finance), plus two duplicate tables that are never
queried directly. A Unity Catalog-style governance layer: table/column
permissions plus an audit trail. Four tables carry unknown/missing
fields (unknown freshness, unknown schema, or both) — the agent must
never guess them. The source data is messy on purpose: descriptions
carry PII (redacted before any draft), and "revenue" is defined two
ways — net revenue after returns in sales, gross invoiced revenue in
finance — so a request that needs both definitions pauses.

## Verified numbers

Frozen 48-case eval, deterministic, seed 42. Stub reasoner only;
$0.00 spend. Golden set hash-locked (`eval/golden.sha256`); the eval
refuses to run on a tampered set.

| Metric | Result |
| --- | --- |
| Agreement with analyst gold labels | **48/48 (100%)** |
| False auto-deploys | **0** |
| False holds | **0** |
| Abstention (insufficient evidence) | **6/6** |
| Fabrication blocked | **6/6** |
| Injection blocked | **6/6** |
| Pause detection (policy violations) | **4/4** |
| Gates checked | **48/48** |
| Stub spend | **$0.00** |

Eval split: clean 12, misrouted/duplicate 8, remediation 6,
insufficient-evidence 6, fabrication 6, injection 6, pause 4.

| Check | Result |
| --- | --- |
| Tests | **75 passed** |
| Ruff check + format | clean |
| Golden set SHA-256 | `193d634f06d8f74db911e5c23468cd5ef342e04ed32612b98f4e3c5806950804` |
| MCP stdio smoke test | initializes as `lakehouse-solutions-agent`, `tools/list` shows exactly 3 tools |

## Reproduce

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .            # no runtime dependencies
pip install ruff pytest     # dev only
ruff check . && ruff format --check .
pytest -q                   # 75 tests
python eval/run_eval.py     # stub eval; reproduces eval/report.json exactly
```

Rebuild the golden set (deterministic, seed 42) and re-hash it:

```bash
python eval/build_golden.py
sha256sum eval/golden.json  # must match eval/golden.sha256
```

## MCP server

Stdio JSON-RPC 2.0, no external dependencies, exposing exactly the
three tools:

```bash
python -m lakehouse_solutions.mcp_server
# {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {...}}
# {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
```

It initializes under the name `lakehouse-solutions-agent`.

## Live mode (optional, never used by the eval)

Haiku only (`claude-haiku-4-5`, $1/$5 per million tokens), a $1.00/day
spend ledger, unknown models refused, refuses without an
`ANTHROPIC_API_KEY`. Install with `pip install '.[live]'`. Only the
refusal paths are tested — live mode has never called a real API in
this repo.

```bash
ANTHROPIC_API_KEY=... python -c "
from lakehouse_solutions.agent import SolutionsAgent
agent = SolutionsAgent(mode='live')
"
```

## Honest limits

- **Synthetic eval.** The 48 cases are frozen and synthetic; 48/48
  measures the stub reasoner against those cases, not real-world
  performance.
- **One signal per case.** Each eval case carries exactly one
  distinguishing signal, by design. Real requests carry several at
  once, and the stub has not been measured on those.
- **Live mode never called a real API.** Only its refusal paths are
  tested (no key, unknown model, cap reached, package absent). Live
  decision quality is unmeasured.
- **No Databricks affiliation.** No Spark, Unity Catalog, Delta Lake,
  or Agent Bricks production experience, and no Databricks platform
  experience at all. The governance layer is Unity Catalog-*style*,
  the stages are Spark-*style*, the query is Genie-*style* — all
  synthetic analogues, not the real systems.
- **Stub SQL is evidence, not execution.** The NL-to-SQL step builds a
  query string over one governed table; nothing executes it against a
  real catalog.
