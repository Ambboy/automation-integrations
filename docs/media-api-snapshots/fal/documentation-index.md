# fal: Documentation

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

## Documentation

- [Documentation](https://fal.ai/docs/documentation/index.md): Learn how to build and deploy AI applications with fal
- [Why fal?](https://fal.ai/docs/documentation/why-fal.md): Industry-leading inference speed for generative AI, trusted by top AI applications
- [Quick Start](https://fal.ai/docs/documentation/quickstart.md): Get started with fal in minutes
- [Support](https://fal.ai/docs/documentation/model-apis/support.md): Support documentation for fal.ai AI APIs. Developer guide with examples, best practices, and implementation details.

### Setting Up

- [Accounts and Identity](https://fal.ai/docs/documentation/setting-up/accounts-and-identity.md): Set up your fal account, choose between personal and team workspaces, and understand how identity works on the platform.
- [Teams](https://fal.ai/docs/documentation/setting-up/teams.md): Create shared workspaces with their own API keys, deployments, and billing. Manage members, roles, and understand how request attribution works.
- [Get Your API Key](https://fal.ai/docs/documentation/setting-up/authentication/index.md): Create an API key to authenticate your requests to fal
- [genmedia CLI](https://fal.ai/docs/documentation/setting-up/genmedia.md): An agent-first command-line tool for running fal models from any terminal or AI agent
- [Libraries, APIs, and Community](https://fal.ai/docs/documentation/setting-up/resources.md): Client libraries, open-source packages, API references, and community links for building with fal.

#### MCP

- [fal MCP server](https://fal.ai/docs/documentation/setting-up/mcp.md): Connect the fal MCP server to ChatGPT, Claude, Claude Code, Codex CLI, Cursor, and other clients using OAuth.
- [MCP setup for ChatGPT](https://fal.ai/docs/documentation/setting-up/mcp/chatgpt.md): Install the fal plugin in ChatGPT, or connect the fal MCP server with developer mode.
- [MCP setup for Claude](https://fal.ai/docs/documentation/setting-up/mcp/claude.md): Connect Claude to the fal MCP server with browser sign-in, then find models and generate media.
- [MCP setup for Claude Code](https://fal.ai/docs/documentation/setting-up/mcp/claude-code.md): Add the fal MCP server to Claude Code, authenticate through your browser, and check the connection.
- [MCP setup for Codex CLI](https://fal.ai/docs/documentation/setting-up/mcp/codex-cli.md): Connect Codex CLI to the fal MCP server using OAuth, without an API key.
- [MCP setup for Cursor](https://fal.ai/docs/documentation/setting-up/mcp/cursor.md): Connect Cursor to the fal MCP server with a remote server URL and browser sign-in.
- [MCP setup for other clients](https://fal.ai/docs/documentation/setting-up/mcp/other-clients.md): Connect any compatible MCP client to fal using Streamable HTTP and OAuth.
- [fal for ChatGPT and Codex](https://fal.ai/docs/documentation/setting-up/codex-plugin.md): Generate and edit images, video, audio, and 3D assets in ChatGPT and Codex with the fal plugin.
- [Platform MCP](https://fal.ai/docs/documentation/setting-up/platform-mcp.md): Connect your AI coding assistant to the fal Platform API MCP and debug your serverless apps from your editor
- [Agent-Readable Surfaces](https://fal.ai/docs/documentation/setting-up/agent-surfaces.md): Plain-text endpoints an AI agent can fetch to learn what fal offers and how to call it
- [fal Agent Plans and Retention](https://fal.ai/docs/documentation/setting-up/agent-plans-and-retention.md): Understand default fal Agent access, optional credit-plan benefits, and Enterprise chat-retention controls.

### Model APIs

- [Model APIs](https://fal.ai/docs/documentation/model-apis/overview.md): Access 1,000+ production-ready AI models through simple API calls
- [Playground](https://fal.ai/docs/documentation/model-apis/playground.md): Test any model with real inputs, see results, and copy working code.
- [Platform Headers](https://fal.ai/docs/documentation/model-apis/common-parameters.md): HTTP headers that control request behavior across all inference methods on fal.
- [Common Model Arguments](https://fal.ai/docs/documentation/model-apis/model-arguments.md): Input parameters like seed, image_size, and safety checker that appear across many models on fal.
- [fal CDN](https://fal.ai/docs/documentation/model-apis/fal-cdn.md): Upload files to fal's CDN to use as inputs when calling models.
- [Data Retention & Storage](https://fal.ai/docs/documentation/model-apis/media-expiration.md): How fal stores your request data and generated media, and how to control retention.
- [File Access Controls](https://fal.ai/docs/documentation/model-apis/file-access-controls.md): Restrict who can access files on the fal CDN with per-user access rules.
- [Concurrency Limits](https://fal.ai/docs/documentation/model-apis/concurrency-limits.md): Understand and manage how many requests you can run simultaneously on fal.
- [Workflow Endpoints](https://fal.ai/docs/documentation/model-apis/workflows.md): Workflows are a way to chain multiple models together to create a more complex pipeline. This allows you to create a single endpoint that can take an input and pass it through multiple models in sequence. This is useful for creating more complex models that require multiple steps, or for creating a…
- [Sandbox](https://fal.ai/docs/documentation/model-apis/sandbox.md): Sandbox is your creative playground for testing and comparing the latest AI models across all popular media generation operations. Compare models side-by-side, estimate costs before running, and share your creations.
- [Pricing](https://fal.ai/docs/documentation/model-apis/pricing.md): How billing works for fal Model APIs.
- [FAQ](https://fal.ai/docs/documentation/model-apis/faq.md)

#### Inference Methods

- [Inference Methods](https://fal.ai/docs/documentation/model-apis/inference/index.md): Learn the different ways to call models on fal
- [Client Setup](https://fal.ai/docs/documentation/model-apis/inference/client-setup.md): Install and configure the fal client library
- [Proxy Setup](https://fal.ai/docs/documentation/model-apis/inference/proxy-setup.md): Keep your API key secure in client-side applications
- [Synchronous Inference](https://fal.ai/docs/documentation/model-apis/inference/synchronous.md): A convenience wrapper for simple blocking calls
- [Streaming Inference](https://fal.ai/docs/documentation/model-apis/inference/streaming.md): Get progressive output as it's generated
- [Real-Time Inference](https://fal.ai/docs/documentation/model-apis/inference/real-time.md): WebSocket-based inference for ultra-low latency applications
- [HTTP over WebSockets](https://fal.ai/docs/documentation/model-apis/inference/websockets.md): For applications that require real-time interaction or handle streaming, fal offers a WebSocket-based integration. This allows you to establish a persistent connection and stream data back and forth between your client and the fal API using the same format as the HTTP endpoints.

##### Async

- [Asynchronous Inference](https://fal.ai/docs/documentation/model-apis/inference/queue.md): The recommended way to call models on fal
- [Webhooks](https://fal.ai/docs/documentation/model-apis/inference/webhooks.md): Webhooks work in tandem with the queue system explained above, it is another way to interact with our queue. By providing us a webhook endpoint you get notified when the request is done as opposed to polling it.
- [Reliability](https://fal.ai/docs/documentation/model-apis/inference/reliability.md): How fal ensures high reliability for your API requests through queueing, automatic retries, and model fallbacks.

#### Errors

- [Model Errors](https://fal.ai/docs/documentation/model-apis/errors.md): Validation and content errors returned by models when inputs don't meet requirements.
- [Request Error Types](https://fal.ai/docs/documentation/model-apis/request-errors.md): Infrastructure-level error types for timeouts, runner failures, and connection errors.

### Serverless

- [Introduction to Serverless](https://fal.ai/docs/documentation/serverless/index.md): Deploy custom AI models on GPU infrastructure that autoscales from zero to thousands of machines.
- [Publishing to the Marketplace](https://fal.ai/docs/documentation/serverless/publishing-to-marketplace.md): Make your serverless app available on the fal Marketplace so anyone can call it with their own API key.
- [Pricing](https://fal.ai/docs/documentation/serverless/pricing.md): How billing works for fal Serverless.
- [FAQ](https://fal.ai/docs/documentation/serverless/faq.md)

#### Development

- [App Lifecycle](https://fal.ai/docs/documentation/development/app-lifecycle.md): The complete lifecycle of a fal app, from writing code to runner shutdown.
- [Calling Your Endpoints](https://fal.ai/docs/documentation/development/calling-your-endpoints.md): How to call your deployed serverless endpoints using the fal client SDKs.
- [Logging](https://fal.ai/docs/documentation/development/logging.md): Understand how logs are captured, scoped, and surfaced across runner logs, request logs, and the Playground.
- [Secrets](https://fal.ai/docs/documentation/development/manage-secrets-securely.md): Store API keys, credentials, and other sensitive configuration securely, accessible to your fal App at runtime.
- [Environment Variables](https://fal.ai/docs/documentation/development/environment-variables.md): Built-in environment variables that fal injects into every runner, covering authentication, app identity, region, lifecycle state, and storage.
- [Request Headers](https://fal.ai/docs/documentation/development/request-headers.md): Access request headers in your fal App for logging, tracing, and per-request logic.

##### Getting Started

- [Installation & Setup](https://fal.ai/docs/documentation/development/getting-started/installation.md): Complete setup guide for the fal CLI and development environment. This guide covers all platforms and authentication methods.
- [Quick Start - Hello World](https://fal.ai/docs/documentation/development/getting-started/quick-start.md): Deploy your first fal app in under 2 minutes. Learn the basics with a simple Hello World example.
- [Deploy Your First Image Generator](https://fal.ai/docs/documentation/development/getting-started/deploy-your-first-image-generator.md): Deploy a text-to-image AI model in under 5 minutes. This tutorial walks you through creating your own image generation API using Stable Diffusion XL.

##### Migrating to fal

- [Migrating to fal](https://fal.ai/docs/documentation/development/migrating-to-fal.md): Bring your existing models and infrastructure to fal with minimal code changes.
- [Migrate an External Docker Server](https://fal.ai/docs/documentation/development/migrate-external-docker-server.md): Deploy an existing Docker-based server (ComfyUI, custom APIs) to fal's serverless platform.
- [Migrate from Replicate](https://fal.ai/docs/documentation/development/migrate-from-replicate.md): A guide for migrating your Replicate Cog models to fal.
- [Migrate from Modal](https://fal.ai/docs/documentation/development/migrate-from-modal.md): A guide for migrating your Modal applications to fal.
- [Migrate from RunPod](https://fal.ai/docs/documentation/development/migrate-from-runpod.md): A guide for migrating your RunPod Serverless workers to fal.
- [Migrate from Baseten](https://fal.ai/docs/documentation/development/migrate-from-baseten.md): A guide for migrating your Baseten models and Chains to fal.

##### Defining Your Environment

- [Environment and Runtime](https://fal.ai/docs/documentation/development/container-setup.md): Choose how to define the environment your fal app runs in.

###### Using a Dockerfile

- [Use a Custom Container Image](https://fal.ai/docs/documentation/development/use-custom-container-image.md): Bring your own Dockerfile to fal for full control over system packages, CUDA versions, and base images.
- [Docker Templates and Best Practices](https://fal.ai/docs/documentation/development/docker-templates.md): Production-ready Dockerfile templates and optimization tips for fal Serverless.
- [Private Docker Registries](https://fal.ai/docs/documentation/development/private-registries.md): How to authenticate with private registries like Docker Hub, Google Artifact Registry, AWS ECR, and Azure Container Registry.

###### Using pip Requirements

- [fal Runtime](https://fal.ai/docs/documentation/development/fal-runtime.md): How to use fal's managed Python runtime to run your models.
- [Import Code](https://fal.ai/docs/documentation/development/import-code.md): Bring local Python packages, modules, files, and external repositories into your fal app's remote environment.

##### Application Setup

- [Application Setup](https://fal.ai/docs/documentation/development/app-setup.md): Prepare your app's runtime environment: load models, download weights, and configure persistent storage.
- [Persistent Storage](https://fal.ai/docs/documentation/development/use-persistent-storage.md): Store model weights, datasets, and files on the shared /data volume that persists across runners and deployments.
- [Download Model Weights and Files](https://fal.ai/docs/documentation/development/download-model-weights-and-files.md): Download model weights, datasets, and external files to your runner using fal toolkit utilities and Hugging Face best practices.

##### Define your endpoints

- [Define Your Endpoints](https://fal.ai/docs/documentation/development/endpoints-overview.md): How to define, structure, and configure the API endpoints your fal App exposes to callers.
- [Handle Inputs and Outputs](https://fal.ai/docs/documentation/development/handle-inputs-and-outputs.md): Define input and output schemas for your fal App endpoints that render correctly in the Playground.
- [Working with Files](https://fal.ai/docs/documentation/development/working-with-files.md): Download input files and return generated outputs from your fal App using the toolkit's file types and download utilities.
- [Streaming Endpoints](https://fal.ai/docs/documentation/development/streaming.md): Stream progressive results to clients using Server-Sent Events (SSE) for real-time feedback during long-running operations.
- [Realtime Endpoints](https://fal.ai/docs/documentation/development/realtime.md): Build low-latency, bidirectional WebSocket endpoints for interactive applications that require persistent connections and back-to-back requests.
- [World Model Accelerator (WMA)](https://fal.ai/docs/documentation/development/wma.md): Experimental fal primitive for interactive world models over a peer-to-peer WebRTC stream between your runners and end users.
- [Test Models and Endpoints](https://fal.ai/docs/documentation/development/test-models-and-endpoints.md): Test your fal App endpoints programmatically using AppClient, which deploys an ephemeral instance and runs your tests against live infrastructure.
- [Add Health Check Endpoint](https://fal.ai/docs/documentation/development/add-health-check-endpoint.md): Add a health check endpoint to your fal app so the platform can detect and replace unhealthy runners.
- [Handle Request Cancellations](https://fal.ai/docs/documentation/development/handle-cancellations.md): Handle in-flight request cancellations to free GPU resources when callers cancel queued or processing requests.

##### Advanced

- [Optimize Routing Behavior](https://fal.ai/docs/documentation/development/advanced/optimize-routing-behavior.md): Use routing hints to direct requests to runners that already have the right model or state loaded in memory.
- [Multi-App Routing](https://fal.ai/docs/documentation/development/multi-app-routing.md): Use a lightweight proxy app to route requests between multiple fal apps based on input characteristics.
- [Use KV Store](https://fal.ai/docs/documentation/development/use-kv-store.md): KVStore is a simple key-value storage for sharing state across serverless runners with zero setup required.
- [Document Your Model](https://fal.ai/docs/documentation/development/document-your-model.md): Attach a human-readable About section to your fal App so callers can understand your model directly from the Playground and the OpenAPI schema.

###### Multi-GPU Workloads

- [Overview](https://fal.ai/docs/documentation/serverless/distributed/overview.md): Learn how to leverage multiple GPUs for faster inference and training with fal.distributed
- [Event Streaming](https://fal.ai/docs/documentation/serverless/distributed/streaming.md): Learn how to stream real-time results during distributed inference and training
- [API Reference](https://fal.ai/docs/documentation/serverless/distributed/api-reference.md): Essential API reference for fal.distributed: the key methods you need to build multi-GPU applications

#### Deployment

- [Deployment Overview](https://fal.ai/docs/documentation/deployment/overview.md): Ship your fal applications to production, manage revisions and environments, configure scaling, and choose the right machine type.
- [Deploy to Production](https://fal.ai/docs/documentation/deployment/deploy-to-production.md): Deploy your fal App to production with persistent URLs, authentication, and automatic scaling.
- [Machine Types](https://fal.ai/docs/documentation/deployment/machine-types.md): Available machine types, specifications, and guidance on choosing the right GPU for your workload.
- [Manage Deployments](https://fal.ai/docs/documentation/deployment/manage-deployments.md): Once your models are deployed to production, you need tools and strategies to manage them effectively. This guide covers listing deployments, monitoring application health, managing multiple versions, and safely removing models.
- [Rollbacks & Revisions](https://fal.ai/docs/documentation/deployment/rollbacks.md): Manage app revisions, roll back to previous versions, and restart runners.
- [Manage Environments](https://fal.ai/docs/documentation/deployment/manage-environments.md): Organize your fal Serverless applications, secrets, and configurations across different stages of your development workflow using environments. Create isolated spaces for development, staging, and production deployments.

##### Runners and Requests

- [Understanding Requests](https://fal.ai/docs/documentation/deployment/requests.md): How requests flow through fal's infrastructure, from submission through queue, dispatch, processing, and retries.
- [Understanding Runners](https://fal.ai/docs/documentation/deployment/runners.md): What runners are, how they start, process requests, scale, and shut down.
- [Debugging Runners](https://fal.ai/docs/documentation/deployment/debug-runners.md): Inspect live runners with an interactive shell or one-off commands using the fal CLI.
- [Caching](https://fal.ai/docs/documentation/deployment/caching.md): How fal's multi-layer caching system reduces cold start times by caching Docker images, model weights, and compiled artifacts.

##### Scaling Your Application

- [Scaling Parameter Reference](https://fal.ai/docs/documentation/deployment/scale-your-application.md): All scaling parameters for controlling runners, cold starts, and costs.
- [Updating Your Configuration](https://fal.ai/docs/documentation/deployment/scaling-configuration.md): How to set scaling parameters via code, CLI, or dashboard -- and how they behave across deploys.

#### Reliability

- [Retries and Error Handling](https://fal.ai/docs/documentation/serverless/reliability/retries.md): How fal retries failed requests, what each status code does to runners, and how to control behavior with response headers.
- [GPU Health](https://fal.ai/docs/documentation/serverless/reliability/gpu-health.md): How fal monitors GPU health, detects failures, and gives you control over runner health through custom health checks.

#### Observability

- [Observability Overview](https://fal.ai/docs/documentation/serverless/observability/monitor-performance.md): Monitor your fal applications using the dashboard, CLI, and programmatic integrations.
- [Debugging with AI](https://fal.ai/docs/documentation/serverless/observability/debug-with-ai.md): Use the Platform MCP to investigate serverless incidents from your AI assistant — grounded in your real requests, logs, analytics, and runner state
- [Aggregate Analytics](https://fal.ai/docs/documentation/serverless/observability/aggregate-analytics.md): Get a cross-app overview of capacity, traffic, and health across every serverless app you own.
- [App Analytics](https://fal.ai/docs/documentation/serverless/observability/app-analytics.md): Monitor your application's performance with real-time metrics and detailed analytics.
- [Runner Analytics](https://fal.ai/docs/documentation/serverless/observability/runner-analytics.md): Debug individual runners with cold start stage breakdowns, live telemetry, per-runner logs, and shell access.
- [Error Analytics](https://fal.ai/docs/documentation/serverless/observability/error-analytics.md): Explore, filter, and debug request errors across your applications.
- [Logs](https://fal.ai/docs/documentation/serverless/observability/logs.md): Explore, filter, share, and export your application logs from the dashboard.
- [App Events](https://fal.ai/docs/documentation/serverless/observability/app-events.md): Track deployments, runner lifecycle, and config changes with a full audit trail.
- [Exporting Metrics](https://fal.ai/docs/documentation/serverless/observability/exporting-metrics.md): Export Prometheus-compatible metrics to Grafana, Datadog, or any monitoring tool.
- [Log Drains](https://fal.ai/docs/documentation/serverless/observability/log-drains.md): Forward application logs to Datadog or any HTTPS endpoint.
- [Slack Notifications](https://fal.ai/docs/documentation/serverless/observability/slack-notifications.md): Receive real-time alerts in Slack when your apps fail to start.

##### OpenTelemetry

- [Custom Traces with OpenTelemetry](https://fal.ai/docs/documentation/serverless/observability/opentelemetry-traces.md): Add OpenTelemetry spans to your fal app to trace inference stages like warmup, diffusion, and image upload
- [Cross-Service Tracing](https://fal.ai/docs/documentation/serverless/observability/opentelemetry-cross-service.md): Propagate trace context between two fal apps so that preprocessing and inference appear as children of a single parent trace
- [OpenTelemetry in Production](https://fal.ai/docs/documentation/serverless/observability/opentelemetry-production.md): Configure sampling, batch export tuning, and graceful flush so your traces hold up under production load

#### Optimizations

- [Optimizing Costs](https://fal.ai/docs/documentation/serverless/optimizations/optimizing-costs.md)

##### Optimizing Cold Starts

- [Optimizing Cold Starts](https://fal.ai/docs/documentation/serverless/optimizations/optimize-cold-starts.md): Understanding cold starts and how to reduce them.
- [Adjust Scaling Parameters](https://fal.ai/docs/documentation/serverless/optimizations/cold-start-scaling.md): Reduce cold starts by keeping warm runners available.
- [Optimize Container Images](https://fal.ai/docs/documentation/serverless/optimizations/optimize-container-images.md): Container optimization is key to achieving faster cold starts, reducing deployment sizes, and improving overall application performance. This guide covers Dockerfile optimization techniques, layer caching strategies, multi-stage builds, and build performance improvements to help you create efficient…
- [Optimize Startup with Compiled Caches](https://fal.ai/docs/documentation/serverless/optimizations/optimize-startup-with-compiled-caches.md): Reduce cold-start time for compiled PyTorch models by sharing Inductor caches across workers.
- [FlashPack](https://fal.ai/docs/documentation/serverless/optimizations/flashpack.md): High-throughput tensor loading for PyTorch -- load models at up to 25Gbps without GDS.
- [Parallel File Loading](https://fal.ai/docs/documentation/serverless/optimizations/parallel-file-loading.md): Speed up model loading by pre-reading files in parallel from /data.

### Compute

- [Introduction to Compute](https://fal.ai/docs/documentation/compute/index.md): Dedicated GPU instances for training, fine-tuning, and workloads that need sustained access to hardware.
- [Quickstart with Compute](https://fal.ai/docs/documentation/compute/quickstart.md): Get up and running with fal Compute in minutes. This guide will walk you through provisioning your first GPU instance and connecting to it.
- [Pricing](https://fal.ai/docs/documentation/compute/pricing.md): How billing works for fal Compute.

### Organizations

- [Organizations](https://fal.ai/docs/documentation/organizations/index.md): Centralized management for teams, billing, and model access across your company.
- [Managing Teams](https://fal.ai/docs/documentation/organizations/managing-teams.md): Control team lifecycle, member management, and organization-wide policies.
- [Model Access Controls](https://fal.ai/docs/documentation/organizations/access-controls.md): Restrict which models your team members can access via the API and Playground.

### fal Agent

- [Introduction to fal Agent](https://fal.ai/docs/documentation/agent/index.md): fal Agent is an AI creative partner that plans and runs generative media work across every top image, video, audio, and 3D model on fal.
- [Quickstart](https://fal.ai/docs/documentation/agent/quickstart.md): Start your first fal Agent chat, attach a reference, review the plan, and download the result.
- [Access and pricing](https://fal.ai/docs/documentation/agent/access-and-pricing.md): How to access fal Agent, what optional credit plans include, and what fal bills for.
- [Assets and characters](https://fal.ai/docs/documentation/agent/assets-and-characters.md): Reuse library media in chats, organize collections, and reference characters and smart entities.
- [Settings](https://fal.ai/docs/documentation/agent/settings.md): Every fal Agent preference: profile, default model, sequencer, notifications, skills, connectors, spending caps, and retention.
- [Retention and data](https://fal.ai/docs/documentation/agent/retention.md): How long fal Agent keeps prompts, generations, and chats, how organizations set a retention policy, and how external content is handled.
- [FAQ](https://fal.ai/docs/documentation/agent/faq.md): Common questions about fal Agent access, models, cost, limits, and programmatic use.

#### Agent SDK

- [Agent SDK](https://fal.ai/docs/documentation/agent/sdk/index.md): Build a TypeScript interface for fal Agent responses, approvals, plans, and generated media.
- [Agent SDK quickstart](https://fal.ai/docs/documentation/agent/sdk/quickstart.md): Install the TypeScript SDK, run your first task, and read the result.
- [Client configuration](https://fal.ai/docs/documentation/agent/sdk/configuration.md): Configure authentication, transport, retries, and the public Agent exports.
- [Responses and recovery](https://fal.ai/docs/documentation/agent/sdk/responses.md): Submit tasks, observe response snapshots, and recover without creating duplicate work.
- [Questions and approvals](https://fal.ai/docs/documentation/agent/sdk/inputs.md): Answer questions and approvals, then resume the same Agent response.
- [Edit and run plans](https://fal.ai/docs/documentation/agent/sdk/plans.md): Update plan steps with revision checks and approval checkpoints.
- [Media and costs](https://fal.ai/docs/documentation/agent/sdk/media.md): Read completed artifacts, reuse media in follow-ups, and select final results.
- [Conversations and history](https://fal.ai/docs/documentation/agent/sdk/resources.md): Create conversations, read their history, and manage their lifecycle.
- [Projects, documents, and memory](https://fal.ai/docs/documentation/agent/sdk/projects.md): Organize conversations and media, attach documents, and maintain project memory.
- [Models and settings](https://fal.ai/docs/documentation/agent/sdk/settings.md): Choose models, change generation defaults, and update account preferences.
- [Queues and generation runs](https://fal.ai/docs/documentation/agent/sdk/queue.md): Control queued work, handle generation approvals, and inspect or retry a generation attempt.
- [Library assets, collections, and entities](https://fal.ai/docs/documentation/agent/sdk/library.md): Manage assets, manual and smart collections, and all five smart entity types.
- [Skills](https://fal.ai/docs/documentation/agent/sdk/skills.md): Discover, install, edit, and activate skills for fal Agent conversations.
- [Tool activity](https://fal.ai/docs/documentation/agent/sdk/activity.md): Read tool progress, visible reasoning, and activated skills from response snapshots.
- [Errors and troubleshooting](https://fal.ai/docs/documentation/agent/sdk/errors.md): Distinguish request failures from execution failures and recover without duplicate work.
- [Use the docs with coding agents](https://fal.ai/docs/documentation/agent/sdk/for-agents.md): Give a coding agent the exact guides and references needed to build an Agent SDK integration.

##### Reference

- [Method reference](https://fal.ai/docs/documentation/agent/sdk/methods.md): Signatures, inputs, return types, and guide links for every Agent client method.
- [Type reference](https://fal.ai/docs/documentation/agent/sdk/types.md): Complete field definitions for Agent requests, responses, settings, projects, and library resources.

#### Chats

- [Chat interface](https://fal.ai/docs/documentation/agent/chats/interface.md): The fal Agent shell: sidebar, chat, media rail, history, turn navigation, keyboard shortcuts, notifications, and the installable app.
- [Composer and references](https://fal.ai/docs/documentation/agent/chats/composer.md): Reference models, generations, assets, characters, skills, and connected apps from one palette. Attach files, drag and drop, and paste.
- [Queue and steering](https://fal.ai/docs/documentation/agent/chats/queue.md): Send messages while the agent works, queue follow-ups, stop a running chain, and cancel generations.
- [Sharing and forking](https://fal.ai/docs/documentation/agent/chats/sharing.md): Share a read-only view of a chat with a link, restrict the audience, set an expiry, and fork a chat from any message.

#### How the Agent Works

- [Models and generation](https://fal.ai/docs/documentation/agent/models-and-generation.md): How fal Agent chooses models, validates inputs, runs batches, compares models, and repairs failed runs.
- [Plan cards](https://fal.ai/docs/documentation/agent/plan-cards.md): Review, edit, approve, and version the agent's plan before and during a multi-step run.
- [Spending caps](https://fal.ai/docs/documentation/agent/spending-caps.md): Confirm expensive generations before they run, per media type, with a safety cap in USD.

#### Generations

- [Generations and the media rail](https://fal.ai/docs/documentation/agent/generations/overview.md): How generations appear in the chat and the media rail, and what you can do with each tile.
- [Media viewer](https://fal.ai/docs/documentation/agent/generations/media-viewer.md): Open any generation full screen, zoom, inspect the request, mark it up, and send an edit straight back to the agent.
- [Export](https://fal.ai/docs/documentation/agent/generations/export.md): Download one generation, or export every completed generation in a chat as one ZIP with a folder per batch.

#### Projects

- [Projects](https://fal.ai/docs/documentation/agent/projects/index.md): Group chats, media, documents, characters, and collections under one shared memory.
- [Memory and documents](https://fal.ai/docs/documentation/agent/projects/memory.md): How project memory captures decisions and preferences, and how uploaded documents become project context.

#### Skills

- [Skills](https://fal.ai/docs/documentation/agent/skills/index.md): Skills are Markdown capabilities the agent picks up automatically based on the task. fal ships a set, and you can add your own.
- [Custom skills](https://fal.ai/docs/documentation/agent/skills/custom-skills.md): Write your own skill in the editor or install one from GitHub. Format, fields, references, updates, and limits.

#### Tools

- [Sandbox code execution](https://fal.ai/docs/documentation/agent/tools/sandbox.md): fal Agent runs Python in an isolated sandbox for deterministic media work: ffmpeg cuts, pixel-exact edits, format conversion, and video compositing.
- [Web search and URL reading](https://fal.ai/docs/documentation/agent/tools/web.md): fal Agent can search the public web and read pages in full to ground its work in current information.
- [Video understanding and media download](https://fal.ai/docs/documentation/agent/tools/video-understanding.md): Ask fal Agent questions about a video with timestamps, and bring public media from YouTube, TikTok, or X into the chat.
- [Video sequences](https://fal.ai/docs/documentation/agent/tools/video-sequences.md): Arrange clips into an editable timeline with audio layers, adjust it by hand or through the agent, and export one video file.
- [Connectors](https://fal.ai/docs/documentation/agent/tools/connectors.md): Connect fal Agent to the apps you already use, so it can post results, read documents, and update tasks on your behalf.
- [Training](https://fal.ai/docs/documentation/agent/tools/training.md): Fine-tune a LoRA on your own images from inside a chat, and follow the run with a live loss curve and sample outputs.

### fal Assets

- [Introduction to fal Assets](https://fal.ai/docs/documentation/assets/index.md): Find, organize, and reuse images, videos, audio, and 3D assets from your fal generations and uploads.
- [Quickstart](https://fal.ai/docs/documentation/assets/quickstart.md): Upload a reference, organize it into a collection, find it again, and reuse it in a generation.
- [Access and availability](https://fal.ai/docs/documentation/assets/access.md): Enable fal Assets, choose the right account, and understand team permissions and enterprise access.
- [Reusing assets across fal](https://fal.ai/docs/documentation/assets/reusing.md): Use existing library media as model inputs, Agent attachments, and project references.
- [Sharing collections](https://fal.ai/docs/documentation/assets/sharing.md): Share a manual collection with a viewing link, choose its audience, and manage expiry or revocation.
- [Downloading assets](https://fal.ai/docs/documentation/assets/downloading.md): Download one asset or export selected media as a ZIP.
- [Retention and deletion](https://fal.ai/docs/documentation/assets/retention.md): Understand the difference between organizing media, removing library assets, and deleting or expiring files.
- [Using the Assets API](https://fal.ai/docs/documentation/assets/api.md): Browse, search, register uploads, and organize assets with the fal Platform API.
- [FAQ and troubleshooting](https://fal.ai/docs/documentation/assets/faq.md): Resolve missing assets, search issues, unavailable references, sharing restrictions, and download failures.

#### Your library

- [Adding assets](https://fal.ai/docs/documentation/assets/library/adding.md): Bring generated media and uploaded references into your fal Assets library.
- [Browsing and previewing](https://fal.ai/docs/documentation/assets/library/browsing.md): Navigate your library, adjust the media grid, and inspect images, videos, audio, and 3D assets.
- [Searching and filtering](https://fal.ai/docs/documentation/assets/library/search.md): Search your assets by description, image, or video, and narrow the results with library filters.
- [Generation details and history](https://fal.ai/docs/documentation/assets/library/history.md): Inspect an asset's prompt and metadata, follow its inputs, and find generations that used it.

#### Organizing assets

- [Collections and folders](https://fal.ai/docs/documentation/assets/organizing/collections.md): Group assets into manual collections, organize nested folders, and move media without duplicating it.
- [Smart collections](https://fal.ai/docs/documentation/assets/organizing/smart-collections.md): Save rules that automatically find matching media in your library.
- [Tags and favorites](https://fal.ai/docs/documentation/assets/organizing/tags-and-favorites.md): Label assets across collections and keep frequently used media easy to find.

#### Characters and smart entities

- [Characters and smart entities](https://fal.ai/docs/documentation/assets/entities/index.md): Define reusable characters, props, environments, styles, and scenes with reference images and an @handle.
- [Creating and managing entities](https://fal.ai/docs/documentation/assets/entities/managing.md): Create reusable references, manage their images and handles, and organize associated generations.
- [Using entities in generations](https://fal.ai/docs/documentation/assets/entities/using.md): Reference characters, props, environments, styles, and scenes in Agent and supported model prompts.
