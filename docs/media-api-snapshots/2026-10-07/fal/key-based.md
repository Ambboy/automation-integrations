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

# Key-Based Authentication

Key-based authentication lets you authenticate fal API requests using a secret key generated from the dashboard. This is the recommended authentication method for production applications, CI/CD pipelines, and any environment where you need programmatic access.

Keys are scoped to control what operations they can perform, giving you fine-grained control over access. You can create and manage keys from the fal dashboard at any time.

## Overview

There are two main reasons to use key-based authentication:

1. When calling [ready-to-use models](https://fal.ai/models)
2. In headless remote environments or CI/CD (where GitHub authentication is not available)

## Generating the keys

Navigate to our dashboard keys page and generate a key from the UI [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys)

## Scopes

Scopes provide a way to control the permissions and access level of a given key. By assigning scopes to keys, you can limit the operations that each key can perform. Currently there are only two scopes, `ADMIN` and `API`. If you are just consuming [ready-to-use models](https://fal.ai/models), we recommend that you use the `API` scope.

### API scope

* Grants access to all models on fal, including ready-to-use models and your own deployed endpoints.
* Grants access to API-scoped [Platform APIs](/docs/api-reference/platform-apis/index).

### ADMIN scope

* Grants full access to private models.
* Grants full access to CLI operations.
* Grants access to ready-to-use models.
* Grants access to API-scoped and ADMIN-scoped [Platform APIs](/docs/platform-apis).
