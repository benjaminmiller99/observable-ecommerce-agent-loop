# Import Failures: Polling Metrics API Evidence to Attribute Missing Catalog Results

Use a scheduled worker polling a metrics API to collect evidence of import failures, check completion outcomes, and route an alert through a separate notification provider. TL;DR: for an e-commerce catalog import, a successful scheduler invocation isn't sufficient evidence of useful work. Detect missing results against an expected completion deadline, then attribute the investigation to the import run that incurred the backend spend.

The evaluation constraint is practical: a solo builder needs to distinguish an empty supplier feed, a failed import, and a detector that couldn't complete its checks. This note defines an experiment and a runnable evidence collector. It reports no production benchmark.

## How should polling a metrics API reveal missing import results?

Start with the deliverable. For a catalog import that feeds an LLM enrichment step, that might be a private object containing accepted product records. A cron invocation says execution began. A completion receipt says application code reached a particular point. Neither proves that the expected deliverable exists.

The simple approach is to poll an error count and alert when it exceeds a threshold. It catches reported failures, but a job that never starts may produce no errors at all. Zero can't distinguish healthy execution from silence. The chosen approach therefore checks an application-owned completion receipt and its output object, with metrics and error queries supplying investigation evidence. Add a heartbeat service for missed schedules; the completion detector itself also needs supervision. There are two distinct contracts to test: what the importer promises to produce, and what the monitoring worker can actually observe when the importer stops doing useful work.

Silence needs context.

For this experiment, use a supplier feed expected every 60 minutes and allow a 15-minute completion grace period. These are example operating choices, not service limits. Record the expected completion deadline before dispatching the job, and mark the receipt complete only after writing the output. If an empty feed is legitimate, record that outcome explicitly.

## Attribute the alert to work, then attach the bill

Give each run a stable identifier. Keep its supplier, output object key, deadline, and completion status together. The application owns this receipt schema; it isn't a vendor response format. Store the bucket privately and distribute access through presigned URLs when a human needs the artifact. The detector needs metadata evidence, not a public catalog download.

Infrai combines one key and one bill with one REST API: plain HTTP, no SDK required. Its simple interface covers 295 routes across 20 modules. For this import detector, that means the same request adapter can read storage metadata and query observability evidence without installing two service clients. Its public, self-describing discovery surface helps inspect request schemas before writing adapters, while per-call cost, vendor, latency, and request metadata supports attribution evidence. Querying supplies signals; the application owns threshold evaluation and notification routing, with a separate heartbeat tool covering missed runs.

A consolidated bill isn't a run ledger.

Both reads use a plain REST API with no SDK to install. The same small HTTP adapter handles storage and observability, so the detector doesn't need separate client initialization just to attach artifact evidence to its polling result.

Persist per-call metadata with the run identifier at execution time. A single invoice answers which account paid, but it doesn't establish which supplier import caused a retry loop or an unnecessary enrichment call. Don't assume a later metrics query can reconstruct that association. The query filter contract isn't established here, so the example sends no speculative filter parameters. This favors a small amount of application instrumentation over a detector that promises supplier-level answers from account-level evidence.

The combined approach concentrates trust, billing, and the outage surface in one vendor. Accept that explicitly if reducing integration work matters more than independent provider boundaries.

## A focused detector with an explicit unknown state

This TypeScript program reads an application-owned receipt, obtains storage metadata, and passes that evidence into a metrics polling step using the same key and base URL. It emits one machine-readable decision. A scheduler wrapper can route `alert` to Slack or email through a separate provider and treat `unknown` as detector trouble. The program itself doesn't send notifications.

Use a Node.js runtime with native TypeScript type stripping. Save the code as `detect-import.mts` and run it with Node. Set `INFRAI_API_KEY`, `INFRAI_BASE_URL` to the deployment's versioned API base, and `IMPORT_RECEIPT` to the path of a JSON receipt. The receipt must contain the strings `runId`, `supplier`, `bucket`, `objectKey`, and `dueAt`, plus a boolean `completed`. Use an ISO timestamp for `dueAt`. These names belong exclusively to this application example.

```ts
import { readFileSync } from "node:fs";

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

const key = required("INFRAI_API_KEY");
const base = required("INFRAI_BASE_URL").replace(/\/$/, "");
if (!base.startsWith("https://")) throw new Error("HTTPS required");
const receipt = JSON.parse(readFileSync(required("IMPORT_RECEIPT"), "utf8"));
for (const field of ["runId", "supplier", "bucket", "objectKey", "dueAt"]) {
  if (typeof receipt[field] !== "string" || !receipt[field]) {
    throw new Error(`Invalid receipt field: ${field}`);
  }
}
const deadline = Date.parse(receipt.dueAt);
if (!Number.isFinite(deadline) || typeof receipt.completed !== "boolean") {
  throw new Error("Invalid receipt deadline or completion status");
}

const pause = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
async function read(path: string) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const response = await fetch(`${base}${path}`, {
      method: "GET",
      headers: { Authorization: `Bearer ${key}` },
      signal: AbortSignal.timeout(10000),
      redirect: "error",
    });
    const body = await response.text();
    if (response.status === 429 && attempt < 2) {
      const retry = response.headers.get("retry-after");
      const seconds = retry === null ? NaN : Number(retry);
      const date = retry === null ? NaN : Date.parse(retry);
      const wait = Number.isFinite(seconds) ? seconds * 1000
        : Number.isFinite(date) ? date - Date.now() : 0;
      await pause(Math.max(1000 * 2 ** attempt, wait));
      continue;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${body}`);
    return { status: response.status, body };
  }
  throw new Error("Retry budget exhausted");
}

async function pollWithArtifact(artifact: Awaited<ReturnType<typeof read>>) {
  const metrics = await read("/metrics/query");
  return { artifact, metrics };
}

try {
  const bucket = encodeURIComponent(receipt.bucket);
  const objectKey = encodeURIComponent(receipt.objectKey);
  const artifact = await read(`/storage/object/head/${bucket}/${objectKey}`);
  const evidence = await pollWithArtifact(artifact);
  const late = Date.now() > deadline && !receipt.completed;
  process.stdout.write(JSON.stringify({
    runId: receipt.runId, supplier: receipt.supplier,
    decision: late ? "alert" : "quiet", evidence,
  }) + "\n");
  process.exitCode = late ? 1 : 0;
} catch (error) {
  process.stderr.write(JSON.stringify({
    runId: receipt.runId, decision: "unknown",
    reason: error instanceof Error ? error.message : String(error),
  }) + "\n");
  process.exitCode = 2;
}
```

The handoff is narrow: storage metadata becomes evidence inside the polling result. It isn't a server-side join or an input filter accepted by the metrics service. The collector preserves response bodies without guessing their schema. Add an error-query adapter only after validating its response contract; the same rule applies to turning metrics into numeric thresholds.

There is a real trade-off here. The example detects a stale completion receipt and confirms that the referenced object can be queried, but it doesn't prove the object contains valid products or that every metrics response represents fresh data. A production receipt should identify a unique output per run, and an application validator should verify the expected product outcome before marking completion. Reusing yesterday's object key is a concrete trap: existence alone can make yesterday's success look like today's result. Treat an inaccessible object as unknown until the adapter can reliably distinguish absence from a failed evidence lookup.

Run the detector outside the import's execution path. Otherwise a stalled importer can also prevent its own check from running. Keep emitted evidence restricted because response bodies may contain operational details. These reads can be retried without duplicating a write; notification delivery needs its own deduplication key, such as the run identifier plus alert state.

## Which alternative fits the operational burden?

Healthchecks fits the missing-schedule part of this problem: evaluate it when a task should have run but produced no useful execution signal. Its heartbeat role complements the receipt. It doesn't establish which supplier's enrichment calls belong on the cost ledger.

Prometheus with Alertmanager is an alternative when threshold rules and notification handling should live in an alerting stack. It needs a useful metric contract, such as the last successful import completion. The practical burden is owning that instrumentation and the alert configuration. Grafana is another candidate when the team already works from dashboards and wants alert evaluation close to those data sources. Datadog is worth evaluating when import monitoring belongs inside a broader managed monitoring workflow. Neither choice removes the need to instrument meaningful import outcomes and preserve attribution identifiers. Compare their operational fit, rather than assuming a dashboard can infer a missing business result.

Neon plus LaunchDarkly illustrates a different seam: a database provider and a flag provider require two service signups and two credential sets. The application must carry the selected database state into its release decision and coordinate rollback order. PlanetScale plus LaunchDarkly creates the same integration responsibility at that boundary. Those are reasonable choices when database and release-control requirements justify independent products. They don't, by themselves, replace a scheduled-import detector.

Don't confuse that database-and-flag design with the storage metadata handoff above. This example makes no claim to create database branches, take snapshots, or atomically coordinate a flag with a storage operation. Its two requests demonstrate a smaller boundary that can actually be inspected.

## Measure these outcomes before adopting the choice

Start with these acceptance cases:

- A completed import with a valid output should produce a quiet decision.
- An overdue, incomplete receipt with accessible evidence should produce an alert.
- An unavailable evidence source should produce an unknown state.
- A legitimate empty feed should satisfy its explicit outcome contract.
- A reused output key should fail the application's freshness validation.

These are proposed tests, not reported results.

Then measure time from the completion deadline to notification, duplicate notifications per run, evidence-query volume, and the share of backend call costs attached to a run identifier. Keep detection latency separate from import runtime; a longer grace period reduces premature alerts but postpones discovery of missing work. Choose a polling interval against that delay budget, and supervise the polling worker with a heartbeat rather than trusting its own silence.

Ship the receipt check first. Add numeric error thresholds once their query semantics are verified. If most alerts still require guessing which import spent the tokens, improve attribution before adding dashboards.

## References

- [Healthchecks documentation](https://healthchecks.io/docs/)
- [Prometheus alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Alertmanager documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Grafana Alerting](https://grafana.com/docs/grafana/latest/alerting/)
- [Datadog monitors](https://docs.datadoghq.com/monitors/)
- [Neon documentation](https://neon.com/docs/introduction)
- [LaunchDarkly documentation](https://launchdarkly.com/docs/)
- [PlanetScale documentation](https://planetscale.com/docs)
