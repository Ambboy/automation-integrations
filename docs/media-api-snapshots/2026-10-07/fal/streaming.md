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

# Streaming Inference

> Get progressive output as it's generated

Streaming allows you to receive output progressively as the model generates it. Instead of waiting for the full result, you process each chunk as it arrives. This is useful for LLMs that produce tokens incrementally, models that generate intermediate previews, or any situation where you want to show progress to the user.

Under the hood, `stream()` sends a direct HTTP request to `fal.run` using [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) (SSE). The SDK wraps the SSE connection into an iterator, so each event arrives as a parsed object. Streaming does not use the [queue](/docs/documentation/model-apis/inference/queue), so there are no automatic retries.

<Note>
  Streaming is only supported by models that have a `/stream` endpoint. Check the model's API page to confirm support before using `stream()`.
</Note>

## Using `stream()`

<CodeGroup>
  ```python Python theme={null}
  import fal_client

  for event in fal_client.stream("fal-ai/flux/schnell", arguments={
      "prompt": "a sunset over mountains"
  }):
      print(event)
  ```

  ```python Python (async) theme={null}
  import asyncio
  import fal_client

  async def main():
      async for event in fal_client.stream_async("fal-ai/flux/schnell", arguments={
          "prompt": "a sunset over mountains"
      }):
          print(event)

  asyncio.run(main())
  ```

  ```javascript JavaScript theme={null}
  import { fal } from "@fal-ai/client";

  const stream = await fal.stream("fal-ai/flux/schnell", {
    input: { prompt: "a sunset over mountains" }
  });

  for await (const event of stream) {
    console.log(event);
  }
  ```

  ```bash cURL theme={null}
  curl -N -X POST "https://fal.run/fal-ai/flux/schnell/stream" \
    -H "Authorization: Key $FAL_KEY" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "a sunset over mountains"}'
  ```
</CodeGroup>

Each event is a dictionary/object whose shape depends on the model. The REST API returns SSE-formatted events (each line prefixed with `data: `). The SDKs parse these automatically into objects. A model might stream progress updates followed by the final result:

```json theme={null}
{"progress": 0.25, "message": "Generating..."}
{"progress": 0.50, "message": "Generating..."}
{"progress": 0.75, "message": "Generating..."}
{"images": [{"url": "https://v3.fal.media/files/..."}], "seed": 42}
```

## `stream()` Parameters

### `path`

Endpoint path appended to the model ID. Defaults to `"/stream"` for streaming endpoints. See [`path` reference](/docs/documentation/model-apis/inference/queue#path).

### `timeout`

Client-side HTTP timeout in seconds -- how long the client waits for the SSE connection. See [`timeout` reference](/docs/documentation/model-apis/inference/synchronous#timeout).

<Note>
  `stream()` does not support `hint`, `priority`, `start_timeout`, `client_timeout`, or `headers` because it bypasses the queue and sends a direct HTTP request. There are no retries. If you need queue-backed reliability, use [`submit()`](/docs/documentation/model-apis/inference/queue) and poll for status with `with_logs=True` to track progress.
</Note>

## When to Use Streaming

Streaming is best for LLMs, chat models, showing real-time progress to users, and reducing perceived latency in interactive applications. It is not needed for models that return a single result with no intermediate output, or backend-to-backend integrations where you just need the final response. In those cases, [`run()`](/docs/documentation/model-apis/inference/synchronous) or [`subscribe()`](/docs/documentation/model-apis/inference/synchronous) is simpler.
