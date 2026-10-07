> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

> ## Agent Instructions
> fal has two developer products. Model APIs run hosted models through an API key. fal Serverless deploys your own Python apps and models on fal GPUs.
> To call a hosted model, start with the [Quick Start](https://fal.ai/docs/documentation/quickstart.md) and the [Model APIs overview](https://fal.ai/docs/documentation/model-apis/overview.md).
> To deploy your own model with fal Serverless, start with these pages:
> - [Introduction to Serverless](https://fal.ai/docs/documentation/serverless/index.md): What fal Serverless is and the three ways to deploy on it.
> - [Installation & Setup](https://fal.ai/docs/documentation/development/getting-started/installation.md): Install the fal CLI with `pip install fal` and authenticate.
> - [Quick Start](https://fal.ai/docs/documentation/development/getting-started/quick-start.md): Build a Hello World app, test it with `fal run`, and ship it with `fal deploy`.
> - [App Lifecycle](https://fal.ai/docs/documentation/development/app-lifecycle.md): How a `fal.App` goes from code to running runners.
> - [Define Your Endpoints](https://fal.ai/docs/documentation/development/endpoints-overview.md): Structure the API endpoints that your app exposes.
> - [Deploy to Production](https://fal.ai/docs/documentation/deployment/deploy-to-production.md): Persistent URLs, authentication modes, and automatic scaling.
> - [Machine Types](https://fal.ai/docs/documentation/deployment/machine-types.md): Available GPU and CPU machine types and how to choose one.
> - [Pricing](https://fal.ai/docs/documentation/serverless/pricing.md): Per-second billing and the runner states that are billed.
> - [Scaling Parameter Reference](https://fal.ai/docs/documentation/deployment/scale-your-application.md): Parameters that control runners, concurrency, and scale to zero.
> - [Optimizing Cold Starts](https://fal.ai/docs/documentation/serverless/optimizations/optimize-cold-starts.md): Causes of cold starts and ways to make them shorter.
> - [Examples](https://fal.ai/docs/examples/index.md): Complete Serverless apps for image, video, audio, 3D, realtime, and multi-GPU workloads.
> - [Migrating to fal](https://fal.ai/docs/documentation/development/migrating-to-fal.md): Guides to move an existing Docker server or an app from another platform to fal.
> fal Serverless deploys need access that the fal team approves for each account. Request access at https://fal.ai/dashboard/serverless-get-started.

# Platform MCP

> Connect your AI coding assistant to the fal Platform API MCP and debug your serverless apps from your editor

fal provides a second [MCP](https://modelcontextprotocol.io) server — the **Platform API MCP** — focused on operating and debugging your fal account. Where the [fal MCP](/docs/documentation/setting-up/mcp) lets your assistant *build with models* (search, schemas, inference), this server lets it *inspect your serverless apps*: requests, logs, error analytics, deploy and revision history, runner state, queue depth, spend, and files.

Connect it to Claude Code, Cursor, or any MCP-compatible client with your own [API key](/docs/documentation/setting-up/authentication/index), then ask things like *"why did my last request to my-app fail?"* — your assistant walks the same debugging steps you would: find the failing request, read its logs, check whether it's widespread, correlate with recent deploys and runner state.

The server is hosted at `https://api.fal.ai/v1/mcp/platform` and is **read-only**: it can observe your account but never change it.

<Note>
  This separate endpoint still requires a fal API key with the permissions needed by its tools. The OAuth model-generation relay does not replace Platform MCP authentication. Prefer a **Read-only** key preset for account reads. The default **API** preset covers model requests and some serverless request and metric tools; other account reads need additional permissions. If you don't have one yet, [create one here](https://fal.ai/dashboard/keys).
</Note>

## Setup

<Tabs>
  <Tab title="Claude Code">
    Run this command in your terminal:

    ```bash theme={null}
    claude mcp add --transport http fal-platform \
      https://api.fal.ai/v1/mcp/platform \
      --header "Authorization: Key YOUR_FAL_KEY"
    ```
  </Tab>

  <Tab title="Cursor">
    <Steps>
      <Step title="Open MCP Settings">
        Use `Cmd+Shift+P` (`Ctrl+Shift+P` on Windows) and search for **"Open MCP settings"**.
      </Step>

      <Step title="Add the fal Platform server">
        Add the following to your `mcp.json` file:

        ```json theme={null}
        {
          "mcpServers": {
            "fal-platform": {
              "url": "https://api.fal.ai/v1/mcp/platform",
              "headers": {
                "Authorization": "Key YOUR_FAL_KEY"
              }
            }
          }
        }
        ```
      </Step>

      <Step title="Restart Cursor">
        Save the file and restart Cursor to activate the connection.
      </Step>
    </Steps>
  </Tab>

  <Tab title="Other MCP Clients">
    The Platform API MCP uses the **Streamable HTTP** transport at:

    ```
    https://api.fal.ai/v1/mcp/platform
    ```

    Authentication is via the `Authorization` header with the platform's `Key` scheme:

    ```
    Authorization: Key YOUR_FAL_KEY
    ```

    Any MCP client that supports Streamable HTTP transport can connect. Refer to your client's documentation for the exact configuration format.
  </Tab>
</Tabs>

<Note>
  Note the auth scheme: this server uses `Authorization: Key YOUR_FAL_KEY` (the Platform API's native scheme), not `Bearer`. You can connect both fal MCP servers side by side — they complement each other.
</Note>

***

## Available Tools

The server exposes 16 tools: eleven serverless debugging tools, one model-request tool, and a four-tool discovery gateway that opens up the rest of the Platform API (compute, workflows, keys, account, organization, storage) without bloating your assistant's context.

### Serverless debugging

| Tool | What it does |
| - | - |
| **`list_apps`** | List your apps with the identifiers every other tool accepts; add `expand=endpoints` for each app's route-level endpoint ids |
| **`fetch_requests`** | List recent requests for your endpoint(s) with status, timings, and optional input/output payloads — the grounding step of any debugging session |
| **`fetch_request_logs`** | Search historical app logs; filter by request, level, or free text, with optional stack tracebacks |
| **`get_analytics`** | Aggregated error rates (full error taxonomy), latency percentiles, and cold starts per endpoint over a time window |
| **`fetch_events`** | Operational event history: deployments, config changes, and runner lifecycle transitions — the "what changed around this time?" step |
| **`list_revisions`** | Revision history with deployment status and who deployed — line revision boundaries up against error changes to spot a bad deploy |
| **`get_runner_history`** | Historical runner counts by state (running/idle/pending/draining) — capacity analysis and incident forensics |
| **`get_current_state`** | Real-time snapshot: runner counts by state, concurrency, and current queue size |
| **`get_usage`** | Serverless compute spend and machine-seconds by app (requires `billing:usage:read`) |
| **`list_files`** | List files in your serverless persistent storage |
| **`read_file`** | Read a file from persistent storage (small text artifacts) |

### Model requests

| Tool | What it does |
| - | - |
| **`fetch_model_requests`** | List requests made to fal models; requires `models:requests:read` |

### Discovery

| Tool | What it does |
| - | - |
| **`list_namespaces`** | List the Platform API areas beyond serverless, with operation counts |
| **`search_operations`** | Keyword-search the full operation catalog |
| **`describe_operation`** | Get the parameters and response shape for one operation |
| **`invoke_operation`** | Execute any read-only operation from the catalog with your key |

***

## Examples

<Tip>
  These are quick tastes. For the full guide — the debugging loop, a worked incident example, and a library of prompt recipes — see [Debugging with AI](/docs/documentation/serverless/observability/debug-with-ai).
</Tip>

### Debug a failing endpoint

> "My requests to my-app started failing about an hour ago — figure out why"

The assistant will:

1. Use `fetch_requests` to find the failing requests and their `request_id`s
2. Use `fetch_request_logs` with `traceback: true` to read the stack traces
3. Use `get_analytics` to check whether the failures are widespread or isolated
4. Use `fetch_events` to check whether a deploy or config change lines up with when the failures started
5. Use `get_current_state` to see if runners are healthy right now

### Judge the blast radius

> "Is my-app having an incident or was that one bad request?"

The assistant calls `get_analytics` with the error-count metrics over the incident window and compares error rates against request volume.

### Did a deploy break it?

> "Errors on my-app jumped Tuesday afternoon — did that start with a deploy?"

The assistant uses `list_revisions` to see when each revision went out (and who deployed it), then lines those boundaries up against the error timeline from `get_analytics`.

### Why is my queue growing?

> "Requests to my-app are taking forever — are we capacity-bound?"

The assistant checks the current queue size with `get_current_state`, then compares `get_runner_history` against request volume from `get_analytics` over the same window: a backed-up queue while runner counts stay flat means undercapacity; runners scaling with traffic means a spike.

### Watch spend

> "How much did my serverless apps cost this week, and was any of it surge pricing?"

The assistant calls `get_usage` with a weekly window (`billing:usage:read` permission required).

### Reach beyond serverless

> "List my compute instances"

The assistant uses `search_operations("compute instances")` → `invoke_operation` — no serverless-specific tool needed.

***

## How It Works

The server runs inside the fal Platform API and is fully stateless:

1. Your assistant sends a request to `https://api.fal.ai/v1/mcp/platform` with your API key
2. Tool calls execute against the [Platform API](/docs/api-reference/platform-apis) with that key — normal permissions and ownership scoping apply, so you can only ever see your own account
3. Results are returned to your assistant

Your API key is sent per-request and never stored. Everything is **read-only** in the current version: write operations (like flushing a queue) are listed in the catalog but refuse to execute.

A few things worth knowing:

* **Data freshness** — request, analytics, and usage data are warehouse-backed and can lag real time by a few minutes. Responses carry an `as_of` marker, and the server instructs your assistant not to mistake ingestion lag for "no traffic" during a live incident.
* **Output limits** — large responses are truncated with guidance to narrow the query, so a noisy log search won't flood your assistant's context.
* **Key permissions** — each tool reports the permissions it needs. The **Read-only** preset covers the first-class tools; the **Full** preset also grants broader access. The default **API** preset covers only model requests and some serverless request and metric tools. `get_usage` requires `billing:usage:read`.

***

## FAQ

<Tabs>
  <Tab title="How is this different from the Run MCP?">
    The [fal MCP](/docs/documentation/setting-up/mcp) at `mcp.fal.ai/mcp-relay` is for **building with models**: search the catalog, run inference, upload files. The Platform API MCP is for **operating your account**: debugging serverless apps, checking spend, inspecting infrastructure. Connect both — they don't overlap.
  </Tab>

  <Tab title="Can it change anything on my account?">
    No. The current version is strictly read-only. Write operations are visible in the catalog but refuse invocation. Gated, confirmed actions (like flushing a stuck queue) may come later.
  </Tab>

  <Tab title="Is my API key stored?">
    No. The server is fully stateless. Your key is sent per-request in the `Authorization` header and is never stored.
  </Tab>

  <Tab title="Does it cost extra?">
    No. The MCP server is free — the underlying Platform API calls are the same ones you could make directly with your key.
  </Tab>
</Tabs>
