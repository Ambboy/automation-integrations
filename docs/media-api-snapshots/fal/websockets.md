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

# HTTP over WebSockets

> For applications that require real-time interaction or handle streaming, fal offers a WebSocket-based integration. This allows you to establish a persistent connection and stream data back and forth between your client and the fal API using the same format as the HTTP endpoints.

For applications that require real-time interaction or handle streaming responses, fal provides a WebSocket-based API. This allows you to establish a persistent connection and stream data between your client and the fal platform.

The WebSocket API uses the same request and response format as the standard HTTP endpoints, making it easy to adopt. It is ideal for use cases like streaming LLM outputs, generating audio, or any scenario where you want to receive results incrementally.

<Note>
  This is a different system from [Real-Time Inference](/docs/documentation/model-apis/inference/real-time). Real-time requires a model with an explicit realtime endpoint and speaks msgpack over `wss://fal.run/{model_id}/realtime`. The transport on this page wraps a model's *standard HTTP* endpoint in JSON frames over `wss://ws.fal.run/{model_id}`, so it works with any endpoint — reach for it when you want the ordinary request format over a persistent connection rather than the lowest possible latency.
</Note>

<Warning>
  The Python examples below use `fal.apps.ws`, a helper in the serverless `fal` package that is [marked internal and experimental](https://github.com/fal-ai/fal/blob/main/projects/fal/src/fal/apps.py) in its own docstring — the interface may change without notice. It is not part of `fal-client` or `@fal-ai/client`, so `pip install fal-client` will not provide it; you need `pip install fal`. For production, implement the wire protocol described below against a plain WebSocket client, authenticating with an `Authorization: Key $FAL_KEY` header on the connection handshake — the same header the HTTP endpoints take.
</Warning>

### WebSocket Endpoint

To utilize the WebSocket functionality, use the `wss` protocol with the `ws.fal.run` domain:

```
wss://ws.fal.run/{model_id}
```

### Communication Protocol

Once connected, the communication follows a specific protocol with JSON messages for control flow and raw data for the actual response stream:

1. **Payload Message:** Send a JSON message containing the payload for your application. This is equivalent to the request body you would send to the HTTP endpoint.

2. **Start Metadata:** Receive a JSON message containing the HTTP response headers from your application. This allows you to understand the type and structure of the incoming response stream.

3. **Response Stream:** Receive the actual response data as a sequence of messages. These can be binary chunks for media content or a JSON object for structured data, depending on the `Content-Type` header.

4. **End Metadata:** Receive a final JSON message indicating the end of the response stream. This signals that the request has been fully processed and the next payload will be processed.

### Example Interaction

Here's an example of a typical interaction with the WebSocket API:

**Client Sends (Payload Message):**

```json theme={null}
{"prompt": "generate a 10-second audio clip of a cat purring"}
```

**Server Responds (Start Metadata):**

```json theme={null}
{
  "type": "start",
  "request_id": "5d76da89-5d75-4887-a715-4302bf435614",
  "status": 200,
  "headers": {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Transfer-Encoding": "chunked",
    // ...
  }
}
```

**Server Sends (Response Stream):**

```
<binary audio data chunk 1>
<binary audio data chunk 2>
...
<binary audio data chunk N>
```

**Server Sends (Completion Message):**

```json theme={null}
{
  "type": "end",
  "request_id": "5d76da89-5d75-4887-a715-4302bf435614",
  "status": 200,
  "time_to_first_byte_seconds": 0.577083
}
```

<Note>
  **Benefits of WebSockets**

  * **Real-time Updates:** Ideal for applications that require immediate feedback, such as interactive AI models or live data visualization.
  * **Efficient Data Transfer:** Enables streaming large data volumes without the overhead of multiple HTTP requests.
  * **Persistent Connection:** Reduces latency and improves performance by maintaining an open connection throughout the interaction.
</Note>

This WebSocket integration provides a powerful mechanism for building dynamic and responsive AI applications on the fal platform. By leveraging the streaming capabilities, you can unlock new possibilities for creative and interactive user experiences.

### Example Program

For instance, should you want to make fast prompts to any LLM, you can use `fal-ai/any-llm`.

```python theme={null}
import fal.apps

with fal.apps.ws("fal-ai/any-llm") as connection:
    for i in range(3):
        connection.send(
            {
                "model": "google/gemini-flash-1.5",
                "prompt": f"What is the meaning of life? Respond in {i} words.",
            }
        )

    # they should be in order
    for i in range(3):
        import json

        response = json.loads(connection.recv())
        print(response)
```

And running this program would output:

```bash theme={null}
{'output': '(Silence)\n', 'partial': False, 'error': None}
{'output': 'Growth\n', 'partial': False, 'error': None}
{'output': 'Personal fulfillment.\n', 'partial': False, 'error': None}
```

### Example Program with Stream

The `fal-ai/any-llm/stream` model is a streaming model that can generate text in real-time. Here's an example of how you can use it:

```python theme={null}
with fal.apps.ws("fal-ai/any-llm/stream") as connection:
    # NOTE: this app responds in 'text/event-stream' format
    # For example:
    #
    #    event: event
    #    data: {"output": "Growth", "partial": true, "error": null}

    for i in range(3):
        connection.send(
            {
                "model": "google/gemini-flash-1.5",
                "prompt": f"What is the meaning of life? Respond in {i+1} words.",
            }
        )

    for i in range(3):
        for bs in connection.stream():
            lines = bs.decode().replace("\r\n", "\n").split("\n")

            event = {}
            for line in lines:
                if not line:
                    continue
                key, value = line.split(":", 1)
                event[key] = value.strip()

            print(event["data"])

        print("----")
```

And running this program would output:

```bash theme={null}
{"output": "Perspective", "partial": true, "error": null}
{"output": "Perspective.\n", "partial": true, "error": null}
{"output": "Perspective.\n", "partial": true, "error": null}
{"output": "Perspective.\n", "partial": false, "error": null}
----
{"output": "Find", "partial": true, "error": null}
{"output": "Find meaning.\n", "partial": true, "error": null}
{"output": "Find meaning.\n", "partial": true, "error": null}
{"output": "Find meaning.\n", "partial": false, "error": null}
----
{"output": "Be", "partial": true, "error": null}
{"output": "Be, love, grow.\n", "partial": true, "error": null}
{"output": "Be, love, grow.\n", "partial": true, "error": null}
{"output": "Be, love, grow.\n", "partial": false, "error": null}
----
```
