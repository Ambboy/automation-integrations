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

# Create Compute Instance

> Creates a new compute instance with the specified configuration and SSH key.

**Requirements:**
- Requires compute permissions (extra_permissions.compute = true)
- Authentication required via admin API key
- Valid SSH public key required for instance access

**Key Features:**
- Create high-performance GPU instances
- Specify sector for InfiniBand configuration (8x H100 only)
- SSH key-based authentication
- Automatic instance provisioning and region assignment
- Idempotent creation with Idempotency-Key header (optional but recommended)

**Common Use Cases:**
- Spin up compute resources for ML training
- Create GPU instances for inference workloads
- Set up development environments with H100 GPUs
- Deploy distributed training with InfiniBand networking

**Instance Types:**
- `gpu_8x_h100_sxm5`: 8x NVIDIA H100 GPUs (high-performance, supports sector configuration for InfiniBand)
- `gpu_1x_h100_sxm5`: 1x NVIDIA H100 GPU (standard)

**Idempotency:**
- Optional Idempotency-Key header prevents duplicate instance creation on retries
- Responses cached for 10 minutes per unique key

See [fal.ai docs](https://fal.ai/docs/documentation/compute) for more details.



## OpenAPI

````yaml /api-reference/platform-apis/openapi/v1.json post /compute/instances
openapi: 3.1.0
info:
  title: Platform APIs
  version: v1
  description: fal REST API for programmatic access to platform resources.
servers:
  - url: https://api.fal.ai/v1
    description: Production server
security: []
paths:
  /compute/instances:
    post:
      tags:
        - Compute
      summary: Create Compute Instance
      description: >-
        Creates a new compute instance with the specified configuration and SSH
        key.


        **Requirements:**

        - Requires compute permissions (extra_permissions.compute = true)

        - Authentication required via admin API key

        - Valid SSH public key required for instance access


        **Key Features:**

        - Create high-performance GPU instances

        - Specify sector for InfiniBand configuration (8x H100 only)

        - SSH key-based authentication

        - Automatic instance provisioning and region assignment

        - Idempotent creation with Idempotency-Key header (optional but
        recommended)


        **Common Use Cases:**

        - Spin up compute resources for ML training

        - Create GPU instances for inference workloads

        - Set up development environments with H100 GPUs

        - Deploy distributed training with InfiniBand networking


        **Instance Types:**

        - `gpu_8x_h100_sxm5`: 8x NVIDIA H100 GPUs (high-performance, supports
        sector configuration for InfiniBand)

        - `gpu_1x_h100_sxm5`: 1x NVIDIA H100 GPU (standard)


        **Idempotency:**

        - Optional Idempotency-Key header prevents duplicate instance creation
        on retries

        - Responses cached for 10 minutes per unique key


        See [fal.ai docs](https://fal.ai/docs/documentation/compute) for more
        details.
      operationId: createComputeInstance
      parameters:
        - schema:
            type: string
            description: Optional idempotency key for safe request retries
            example: 550e8400-e29b-41d4-a716-446655440000
          required: false
          description: Optional idempotency key for safe request retries
          name: Idempotency-Key
          in: header
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                instance_type:
                  type: string
                  enum:
                    - gpu_8x_h100_sxm5
                    - gpu_1x_h100_sxm5
                  description: Type of compute instance to create
                  example: gpu_1x_h100_sxm5
                ssh_key:
                  type: string
                  minLength: 1
                  description: >-
                    SSH public key for accessing the instance (e.g., 'ssh-rsa
                    AAAAB3...')
                  example: ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC... user@host
                sector:
                  type: string
                  enum:
                    - sector_1
                    - sector_2
                    - sector_3
                  description: >-
                    Sector for InfiniBand configuration (only valid with
                    gpu_8x_h100_sxm5)
                  example: sector_1
              required:
                - instance_type
                - ssh_key
              description: Request body for creating a new compute instance with SSH access
            example:
              instance_type: gpu_8x_h100_sxm5
              ssh_key: ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC7Kl4... user@host
              sector: sector_1
      responses:
        '201':
          description: Compute instance created successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                    description: Unique identifier for the compute instance
                    example: inst_abc123xyz
                  instance_type:
                    type: string
                    enum:
                      - gpu_8x_h100_sxm5
                      - gpu_1x_h100_sxm5
                    description: Type of compute instance (GPU configuration)
                    example: gpu_1x_h100_sxm5
                  region:
                    type: string
                    enum:
                      - us-west
                      - us-central
                      - us-east
                      - eu-north
                      - eu-west
                      - other
                    description: Geographical region where the instance is located
                    example: us-west
                  sector:
                    type: string
                    enum:
                      - sector_1
                      - sector_2
                      - sector_3
                    description: >-
                      Sector identifier for instance placement within the region
                      (if applicable)
                    example: sector_1
                  ip:
                    type: string
                    description: >-
                      IP address of the instance (available when instance is
                      ready)
                    example: 203.0.113.42
                  status:
                    type: string
                    enum:
                      - ready
                      - init
                      - pending
                      - provisioning
                      - stopped
                      - unknown
                    description: Current operational status of the instance
                    example: ready
                  creator_user_nickname:
                    type: string
                    description: Nickname of the user who created this instance
                    example: developer
                required:
                  - id
                  - instance_type
                  - region
                  - status
                description: >-
                  Compute instance details including configuration, location,
                  and status
              example:
                id: inst_abc123xyz
                instance_type: gpu_8x_h100_sxm5
                region: us-west
                sector: sector_1
                status: provisioning
                creator_user_nickname: developer
        '400':
          description: Invalid request parameters
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: object
                    properties:
                      type:
                        type: string
                        enum:
                          - authorization_error
                          - validation_error
                          - not_found
                          - rate_limited
                          - server_error
                          - not_implemented
                        description: The category of error that occurred
                      message:
                        type: string
                        description: Human-readable error message
                      docs_url:
                        type: string
                        format: uri
                        description: Link to relevant documentation
                      request_id:
                        type: string
                        description: Unique request identifier for debugging
                    required:
                      - type
                      - message
                    description: Error details
                required:
                  - error
                description: Standard error response format
              example:
                error:
                  type: validation_error
                  message: Invalid request parameters
        '401':
          description: Authentication required
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: object
                    properties:
                      type:
                        type: string
                        enum:
                          - authorization_error
                          - validation_error
                          - not_found
                          - rate_limited
                          - server_error
                          - not_implemented
                        description: The category of error that occurred
                      message:
                        type: string
                        description: Human-readable error message
                      docs_url:
                        type: string
                        format: uri
                        description: Link to relevant documentation
                      request_id:
                        type: string
                        description: Unique request identifier for debugging
                    required:
                      - type
                      - message
                    description: Error details
                required:
                  - error
                description: Standard error response format
              example:
                error:
                  type: authorization_error
                  message: Authentication required
        '403':
          description: Access denied
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: object
                    properties:
                      type:
                        type: string
                        enum:
                          - authorization_error
                          - validation_error
                          - not_found
                          - rate_limited
                          - server_error
                          - not_implemented
                        description: The category of error that occurred
                      message:
                        type: string
                        description: Human-readable error message
                      docs_url:
                        type: string
                        format: uri
                        description: Link to relevant documentation
                      request_id:
                        type: string
                        description: Unique request identifier for debugging
                    required:
                      - type
                      - message
                    description: Error details
                required:
                  - error
                description: Standard error response format
              example:
                error:
                  type: authorization_error
                  message: Access denied
        '429':
          description: Rate limit exceeded
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: object
                    properties:
                      type:
                        type: string
                        enum:
                          - authorization_error
                          - validation_error
                          - not_found
                          - rate_limited
                          - server_error
                          - not_implemented
                        description: The category of error that occurred
                      message:
                        type: string
                        description: Human-readable error message
                      docs_url:
                        type: string
                        format: uri
                        description: Link to relevant documentation
                      request_id:
                        type: string
                        description: Unique request identifier for debugging
                    required:
                      - type
                      - message
                    description: Error details
                required:
                  - error
                description: Standard error response format
              example:
                error:
                  type: rate_limited
                  message: Rate limit exceeded
        '500':
          description: Internal server error
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: object
                    properties:
                      type:
                        type: string
                        enum:
                          - authorization_error
                          - validation_error
                          - not_found
                          - rate_limited
                          - server_error
                          - not_implemented
                        description: The category of error that occurred
                      message:
                        type: string
                        description: Human-readable error message
                      docs_url:
                        type: string
                        format: uri
                        description: Link to relevant documentation
                      request_id:
                        type: string
                        description: Unique request identifier for debugging
                    required:
                      - type
                      - message
                    description: Error details
                required:
                  - error
                description: Standard error response format
              example:
                error:
                  type: server_error
                  message: An unexpected error occurred
      security:
        - adminApiKey: []
components:
  securitySchemes:
    adminApiKey:
      type: apiKey
      in: header
      name: Authorization
      description: >-
        Admin API key must be prefixed with "Key ", e.g. Authorization: Key
        YOUR_ADMIN_API_KEY

````