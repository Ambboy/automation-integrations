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

# Real-Time Inference

> WebSocket-based inference for ultra-low latency applications

Real-time inference uses WebSockets for persistent connections, enabling sub-100ms image generation. This is ideal for interactive applications like real-time creativity tools and camera-based inputs.

Unlike [queue-based inference](/docs/documentation/model-apis/inference), real-time connections bypass the queue entirely and route inputs directly to a runner. This eliminates queue wait time, and because the WebSocket maintains a persistent connection, the runner stays warm for all subsequent messages after the initial connection. The first connection may still incur a cold start if no runner is already available. Only models with an explicit real-time endpoint are supported.

<Warning>
  Only models that explicitly support real-time inference can be used with the realtime client. Standard queue-based models do not have a realtime endpoint.
</Warning>

<Note>
  If the model you want has no realtime endpoint but you still want a persistent connection, see [HTTP over WebSockets](/docs/documentation/model-apis/inference/websockets) — it carries a model's ordinary HTTP request and response format over `wss://ws.fal.run/{model_id}`, and works with any endpoint.
</Note>

## Supported Models

<CardGroup cols={2}>
  <Card title="fast-lcm-diffusion" href="https://fal.ai/models/fal-ai/fast-lcm-diffusion">
    SDXL with Latent Consistency Models
  </Card>

  <Card title="fast-turbo-diffusion" href="https://fal.ai/models/fal-ai/fast-turbo-diffusion">
    Optimized SDXL Turbo
  </Card>
</CardGroup>

***

## Quick Start

<CodeGroup>
  ```javascript JavaScript theme={null}
  import { fal } from "@fal-ai/client";

  const connection = fal.realtime.connect("fal-ai/fast-lcm-diffusion", {
    onResult: (result) => {
      console.log(result);
    },
    onError: (error) => {
      console.error(error);
    },
  });

  connection.send({
    prompt: "a sunset over mountains",
    sync_mode: true,
    image_url: "data:image/png;base64,..."
  });
  ```

  ```python Python theme={null}
  import fal_client

  with fal_client.realtime("fal-ai/fast-lcm-diffusion") as connection:
      connection.send({
          "prompt": "a sunset over mountains",
          "sync_mode": True,
          "image_url": "data:image/png;base64,..."
      })
      result = connection.recv()
      print(result)
  ```

  ```python Python (async) theme={null}
  import asyncio
  import fal_client

  async def realtime():
      async with fal_client.realtime_async("fal-ai/fast-lcm-diffusion") as connection:
          await connection.send({
              "prompt": "a sunset over mountains",
              "sync_mode": True,
              "image_url": "data:image/png;base64,..."
          })
          result = await connection.recv()
          print(result)

  asyncio.run(realtime())
  ```
</CodeGroup>

***

## Performance Tips

For the fastest inference:

* Use **512x512** input dimensions (fastest)
* Provide images as base64 encoded data URLs
* Set `sync_mode: true` to receive base64 encoded responses
* 768x768 and 1024x1024 also work well, but 512x512 is optimal

***

## Keeping API Keys Secure

WebSocket connections from browsers cannot safely embed API keys. There are two approaches for client-side authentication: a proxy URL or a token provider.

### Proxy URL

The simplest approach. Point the client at a server-side proxy that adds your API key:

<CodeGroup>
  ```javascript JavaScript theme={null}
  import { fal } from "@fal-ai/client";

  fal.config({
    proxyUrl: "/api/fal/proxy",
  });

  const connection = fal.realtime.connect("fal-ai/fast-lcm-diffusion", {
    connectionKey: "realtime-demo",
    throttleInterval: 128,
    onResult(result) {
      // handle result
    },
  });
  ```

  ```swift Swift theme={null}
  import FalClient

  let fal = FalClient.withProxy("http://localhost:3333/api/fal/proxy")

  let connection = try fal.realtime.connect(
      to: "fal-ai/fast-lcm-diffusion",
      connectionKey: "realtime-demo",
      throttleInterval: .milliseconds(128)
  ) { result in
      // handle result
  }
  ```
</CodeGroup>

<Card title="Proxy Setup" icon="shield" href="/docs/documentation/model-apis/inference/proxy-setup">
  Learn how to set up a server-side proxy
</Card>

### Token Provider

For more control, use a `tokenProvider` function that fetches short-lived JWT tokens from your backend. This is useful when you need per-user authentication or want to restrict which apps a token can access.

<Warning>
  **Protect your token endpoint with authentication.** The endpoint that generates fal tokens should verify that the request comes from an authenticated user in your application. Without proper authentication, anyone could use your endpoint to generate tokens and consume your fal credits.
</Warning>

**Client-side example:**

```typescript theme={null}
import { fal, type TokenProvider } from "@fal-ai/client";

// app includes the full endpoint path, e.g. "fal-ai/fast-lcm-diffusion/realtime"
const myTokenProvider: TokenProvider = async (app) => {
  const response = await fetch(`/api/fal/token?app=${encodeURIComponent(app)}`);
  const { token } = await response.json();
  return token;
};

const connection = fal.realtime.connect("fal-ai/fast-lcm-diffusion", {
  tokenProvider: myTokenProvider,
  tokenExpirationSeconds: 120, // match the duration from your backend
  onResult: (result) => {
    console.log(result);
  },
});

connection.send({
  prompt: "a cat",
  sync_mode: true,
});
```

Pass `tokenExpirationSeconds` to enable automatic token refresh before expiry. Set it to the same value as the `duration` in your backend's token request. If omitted, auto-refresh is disabled and your `tokenProvider` is called once at connection time.

**Next.js API Route example (`app/api/fal/token/route.ts`):**

```typescript theme={null}
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  // IMPORTANT: Add your own authentication logic here
  // const session = await getServerSession();
  // if (!session) {
  //   return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  // }

  const { searchParams } = new URL(request.url);
  const app = searchParams.get("app");

  if (!app) {
    return NextResponse.json({ error: "Missing app parameter" }, { status: 400 });
  }

  const response = await fetch("https://rest.fal.ai/tokens/realtime", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Key ${process.env.FAL_KEY}`,
    },
    // app includes the full path (e.g. "fal-ai/fast-lcm-diffusion/realtime")
    body: JSON.stringify({
      allowed_apps: [app],
      duration: 120,
    }),
  });

  const data = await response.json();
  return NextResponse.json({ token: data.token });
}
```

<Note>
  The `tokenProvider` also works for streaming with `connectionMode: "client"`:

  ```typescript theme={null}
  const stream = await fal.stream("fal-ai/flux/dev", {
    connectionMode: "client",
    tokenProvider: myTokenProvider,
    input: { prompt: "a cat" },
  });
  ```
</Note>

***

## Differences from Queue-Based Inference

Real-time WebSocket connections bypass the queue and connect directly to a runner. Several request parameters that work with queue-based inference do not apply:

| Parameter | Behavior with Real-Time |
| - | - |
| `start_timeout` | No effect. There is no queue wait |
| `priority` | No effect. No queue ordering |
| `webhook_url` | Not supported. Results stream back over the WebSocket |
| Automatic retries | Not available. Failed messages return errors on the connection |
| `X-Fal-No-Retry` | No effect. No retry mechanism to disable |

## Custom WebSocket Path

By default, the realtime client connects to the `/realtime` path on the app (e.g., `wss://fal.run/fal-ai/my-app/realtime`). If your app exposes a realtime endpoint at a different path, use the `path` option:

```typescript theme={null}
const connection = fal.realtime.connect("fal-ai/my-app", {
  path: "/my-custom-ws",
  onResult: (result) => console.log(result),
});
```

In Python, pass the `path` parameter to `realtime()`:

```python theme={null}
connection = fal_client.realtime("fal-ai/my-app", path="/my-custom-ws", on_result=handle_result)
```

***

## Realtime vs Streaming

Both realtime and [streaming](/docs/documentation/model-apis/inference/streaming) give you faster feedback than polling, but they serve different use cases.

| Feature | Realtime (WebSocket) | Streaming (SSE) |
| - | - | - |
| **Direction** | Bidirectional (client and server) | One-way (server to client) |
| **Connection** | Persistent, reusable | New connection per request |
| **Latency** | Lower (connection reuse) | Higher (new connection each time) |
| **Best for** | Interactive apps, back-to-back requests | Progressive output, previews |
| **Protocol** | Binary msgpack (default, customizable) | JSON over SSE |

Use realtime when clients send multiple requests in quick succession over a persistent connection, like interactive image editing or camera-based inputs. Use streaming when you want to show progressive output from a single request, like image generation previews or LLM tokens.

## Protocol Details

The realtime client uses [msgpack](https://msgpack.org/) for binary serialization by default across all SDKs, which is more efficient than JSON for transmitting image data. In Python, `realtime()` and `realtime_async()` provide a `RealtimeConnection` with `send()` and `recv()` methods. In JavaScript, `fal.realtime.connect()` uses callback-based `onResult` and `onError` handlers.

In the JavaScript client, you can customize the message encoding by passing `encodeMessage` and `decodeMessage` options. For example, to use JSON instead of msgpack:

```typescript theme={null}
const connection = fal.realtime.connect("fal-ai/my-app", {
  encodeMessage: (input) => JSON.stringify(input),
  decodeMessage: (data) => JSON.parse(data),
  onResult: (result) => console.log(result),
});
```

## Video Tutorial

Build a Real-Time AI Image App with WebSockets, Next.js, and fal.ai:

<Frame>
  <iframe className="w-full aspect-video rounded-lg" srcdoc="<style>*{padding:0;margin:0;overflow:hidden}html,body{height:100%}img,span{position:absolute;width:100%;top:0;bottom:0;margin:auto}span{height:1.5em;text-align:center;font:48px/1.5 sans-serif;color:white;text-shadow:0 0 0.5em black}</style><a href='https://www.youtube.com/embed/freyCo3pcz4?si=OFfGsi0xwJVe__Yt&autoplay=1'><img src='/docs/docs/images/video-thumbs/realtime.jpg' alt='YouTube video player'><span>▶</span></a>" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen />
</Frame>
