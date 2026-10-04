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

# Agent-Readable Surfaces

> Plain-text endpoints an AI agent can fetch to learn what fal offers and how to call it

Every part of fal's catalog and documentation is available as plain text, so an AI agent can read it directly instead of scraping HTML. Each surface is a different granularity or format — pick the smallest one that answers the question. All of them are public: no API key, no authentication header.

<Note>
  If your assistant supports the Model Context Protocol, [Run MCP](/docs/documentation/setting-up/mcp) is usually a better fit than fetching these files: it can search models and check schemas on demand rather than loading a whole document.
</Note>

## The Surfaces

| Surface | What it contains |
| - | - |
| [fal.ai/llms.txt](https://fal.ai/llms.txt) | Platform overview: entry points, key concepts, and representative endpoint IDs by category |
| [fal.ai/docs/llms.txt](https://fal.ai/docs/llms.txt) | An index of every documentation page, each linking to a Markdown rendering |
| [fal.ai/docs/llms-full.txt](https://fal.ai/docs/llms-full.txt) | The entire documentation inlined in a single file |
| [fal.ai/docs/sitemap.xml](https://fal.ai/docs/sitemap.xml) | Machine-readable list of every documentation URL |
| `fal.ai/models/<endpoint-id>/llms.txt` | Live schema for one model — see below |

## Per-Model Schemas

The highest-value surface for an agent mid-task is the per-model file. Append `/llms.txt` to the model page URL, `fal.ai/models/<endpoint-id>` — not to a `/playground` or `/api` variant of it:

```
https://fal.ai/models/fal-ai/flux/dev/llms.txt
```

It returns that endpoint's current input and output schema with types, required and optional fields, defaults, value constraints, pricing, and generated snippets for cURL, Python, and JavaScript. Because it is generated from the same metadata the platform serves, it cannot drift from the real endpoint.

This is one small fetch rather than a whole-catalog download, and it is the reliable way to get an exact schema. Endpoint IDs change as models are versioned, so prefer fetching this file over relying on an ID remembered from training data.

## Reading a Documentation Page as Markdown

Any documentation page can be fetched as Markdown by appending `.md` to its URL:

```
https://fal.ai/docs/documentation/model-apis/inference/queue.md
```

## Suggested Order

1. Start at [fal.ai/llms.txt](https://fal.ai/llms.txt) to learn what the platform does and which models fit the task.
2. Find a specific model in the [model gallery](https://fal.ai/explore) or the [documentation index](https://fal.ai/docs/llms.txt).
3. Fetch that model's `llms.txt` for the exact schema, then call it using the [client setup](/docs/documentation/model-apis/inference/client-setup) guide.
