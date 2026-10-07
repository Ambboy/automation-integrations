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

# Authentication

> Platform APIs require API keys for secure access to your user or team's data.

## Generating API Keys

Navigate to the dashboard keys page and generate a key from the UI: [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys)

## Scopes

Platform APIs may require different API key scopes.

[Learn more about key-based authentication and scopes](/docs/documentation/model-apis/authentication/key-based).

<CardGroup cols={2}>
  <Card title="API Scope">
    Most Platform APIs accept **API scope** keys. This scope is suitable for most use cases including model discovery, pricing, and analytics.
  </Card>

  <Card title="Admin Scope">
    Some Platform APIs require **Admin scope** keys for access to sensitive data.
  </Card>
</CardGroup>

<Info>
  Check the specific Platform API documentation to see which scope is required. If you're unsure, start with an API scope key. You can always generate an Admin scope key later if needed.
</Info>

<Warning>
  API keys should be kept secure and never exposed in client-side code or public repositories.
</Warning>

## Authentication Format

Include your API key in the `Authorization` header with the `Key` prefix:

```bash theme={null}
Authorization: Key YOUR_API_KEY
```

For endpoints requiring Admin scope:

```bash theme={null}
Authorization: Key YOUR_ADMIN_API_KEY
```

## Usage Examples

### cURL

Using an API scope key for model listing:

```bash theme={null}
curl -X GET "https://api.fal.ai/v1/models?limit=10" \
  -H "Authorization: Key YOUR_API_KEY"
```

Using an Admin scope key for usage data:

```bash theme={null}
curl -X GET "https://api.fal.ai/v1/models/usage" \
  -H "Authorization: Key YOUR_ADMIN_API_KEY"
```

### Python

Using an API scope key:

```python theme={null}
import requests

headers = {
    "Authorization": "Key YOUR_API_KEY"
}

response = requests.get(
    "https://api.fal.ai/v1/models",
    headers=headers,
    params={"limit": 10}
)

print(response.json())
```

### JavaScript

Using an API scope key:

```javascript theme={null}
const response = await fetch('https://api.fal.ai/v1/models?limit=10', {
  headers: {
    'Authorization': 'Key YOUR_API_KEY'
  }
});

const data = await response.json();
console.log(data);
```

## Best Practices

* Store API keys in environment variables
* Use the minimum required scope for your use case
* Rotate keys regularly
* Keep Admin API keys secure and never expose them client-side

## Troubleshooting

### 401 Unauthorized

* Verify your API key is correct
* Ensure the `Authorization` header includes the `Key` prefix
* Check that your API key hasn't been revoked

### 403 Forbidden

Your API key may not have the required scope for the endpoint. Check the endpoint documentation to determine if it requires an Admin scope key, and generate one from the dashboard if needed.
