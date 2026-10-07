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

# Model search

> 
Unified endpoint for discovering model endpoints. Supports three usage modes:

**1. List Mode** (no parameters):
Paginated list of all available model endpoints with minimal metadata.

**2. Find Mode** (`endpoint_id` parameter):
Retrieve specific model endpoint(s) by ID. Supports single or multiple IDs.

**3. Search Mode** (search parameters):
Filter models by free-text query, category, or status.

**Expansion:**
Use `expand` to include additional data in each model object:
- `openapi-3.0` — full OpenAPI 3.0 schema in the `openapi` field
- `enterprise_status` — enterprise readiness status (`ready` or `pending`) in the `enterprise_status` field

**Examples of `endpoint_id` values:**
- `fal-ai/flux/dev`
- `fal-ai/wan/v2.2-a14b/text-to-video`
- `fal-ai/minimax/video-01/image-to-video`
- `fal-ai/hunyuan3d-v21`

See [fal.ai Model APIs](https://fal.ai/docs/documentation/model-apis/overview) for more details.

**Authentication:** Optional. Providing an API key grants higher rate limits.

**Common Use Cases:**
- Browse available models for integration
- Retrieve metadata for specific endpoints
- Search for models by category or keywords
- Get OpenAPI schemas for code generation
- Build model selection interfaces
    



## OpenAPI

````yaml /api-reference/platform-apis/openapi/v1.json get /models
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
  /models:
    get:
      tags:
        - Models
      summary: Model search
      description: >-

        Unified endpoint for discovering model endpoints. Supports three usage
        modes:


        **1. List Mode** (no parameters):

        Paginated list of all available model endpoints with minimal metadata.


        **2. Find Mode** (`endpoint_id` parameter):

        Retrieve specific model endpoint(s) by ID. Supports single or multiple
        IDs.


        **3. Search Mode** (search parameters):

        Filter models by free-text query, category, or status.


        **Expansion:**

        Use `expand` to include additional data in each model object:

        - `openapi-3.0` — full OpenAPI 3.0 schema in the `openapi` field

        - `enterprise_status` — enterprise readiness status (`ready` or
        `pending`) in the `enterprise_status` field


        **Examples of `endpoint_id` values:**

        - `fal-ai/flux/dev`

        - `fal-ai/wan/v2.2-a14b/text-to-video`

        - `fal-ai/minimax/video-01/image-to-video`

        - `fal-ai/hunyuan3d-v21`


        See [fal.ai Model
        APIs](https://fal.ai/docs/documentation/model-apis/overview) for more
        details.


        **Authentication:** Optional. Providing an API key grants higher rate
        limits.


        **Common Use Cases:**

        - Browse available models for integration

        - Retrieve metadata for specific endpoints

        - Search for models by category or keywords

        - Get OpenAPI schemas for code generation

        - Build model selection interfaces
            
      operationId: getModels
      parameters:
        - schema:
            type: integer
            minimum: 1
            description: >-
              Maximum number of items to return. Actual maximum depends on query
              type and expansion parameters.
            example: 50
          required: false
          description: >-
            Maximum number of items to return. Actual maximum depends on query
            type and expansion parameters.
          name: limit
          in: query
        - schema:
            type: string
            description: Pagination cursor from previous response. Encodes the page number.
            example: Mg==
          required: false
          description: Pagination cursor from previous response. Encodes the page number.
          name: cursor
          in: query
        - schema:
            anyOf:
              - type: string
              - type: array
                items:
                  type: string
            description: >-
              Endpoint ID(s) to retrieve (e.g., 'fal-ai/flux/dev'). Can be a
              single value or multiple values (1-50 models). When combined with
              search params, narrows results to these IDs. Use array syntax:
              ?endpoint_id=model1&endpoint_id=model2
            example:
              - fal-ai/flux/dev
              - fal-ai/flux-pro
          required: false
          description: >-
            Endpoint ID(s) to retrieve (e.g., 'fal-ai/flux/dev'). Can be a
            single value or multiple values (1-50 models). When combined with
            search params, narrows results to these IDs. Use array syntax:
            ?endpoint_id=model1&endpoint_id=model2
          name: endpoint_id
          style: form
          explode: true
          in: query
        - schema:
            type: string
            description: >-
              Free-text search query to filter models by name, description, or
              category
            example: text to image
          required: false
          description: >-
            Free-text search query to filter models by name, description, or
            category
          name: q
          in: query
        - schema:
            type: string
            description: >-
              Filter by category (e.g., 'text-to-image', 'image-to-video',
              'training')
            example: text-to-image
          required: false
          description: >-
            Filter by category (e.g., 'text-to-image', 'image-to-video',
            'training')
          name: category
          in: query
        - schema:
            type: string
            enum:
              - active
              - deprecated
            description: Filter models by status - omit to include all statuses
            example: active
          required: false
          description: Filter models by status - omit to include all statuses
          name: status
          in: query
        - schema:
            anyOf:
              - type: string
              - type: array
                items:
                  type: string
            description: >-
              Fields to expand in the response. Supported values: 'openapi-3.0'
              (includes full OpenAPI 3.0 schema in 'openapi' field),
              'enterprise_status' (includes enterprise readiness status)
            example:
              - openapi-3.0
              - enterprise_status
          required: false
          description: >-
            Fields to expand in the response. Supported values: 'openapi-3.0'
            (includes full OpenAPI 3.0 schema in 'openapi' field),
            'enterprise_status' (includes enterprise readiness status)
          name: expand
          style: form
          explode: true
          in: query
      responses:
        '200':
          description: Successfully retrieved model endpoints
          content:
            application/json:
              schema:
                type: object
                properties:
                  models:
                    type: array
                    items:
                      type: object
                      properties:
                        endpoint_id:
                          type: string
                          description: >-
                            Stable identifier used to call the model (e.g.,
                            'fal-ai/wan/v2.2-a14b/text-to-video',
                            'fal-ai/minimax/video-01/image-to-video',
                            'fal-ai/hunyuan3d-v21')
                        metadata:
                          type: object
                          properties:
                            display_name:
                              type: string
                              description: >-
                                Human-readable label shown on Explore/Model
                                pages
                            category:
                              type: string
                              description: >-
                                Model category (e.g., 'text-to-image',
                                'image-to-video', 'text-to-video',
                                'image-to-3d', 'training')
                            description:
                              type: string
                              description: >-
                                Brief description of the model's capabilities
                                and use cases
                            status:
                              type: string
                              enum:
                                - active
                                - deprecated
                              description: >-
                                'active' or 'deprecated'. Newest models are
                                surfaced in Explore and may be flagged as
                                'new/beta' in tags
                            tags:
                              type: array
                              items:
                                type: string
                              description: >-
                                Freeform tags such as 'new', 'beta', 'pro', or
                                'turbo' (Explore badges)
                            updated_at:
                              type: string
                              description: >-
                                ISO8601 timestamp of when the model was last
                                updated
                            is_favorited:
                              type:
                                - boolean
                                - 'null'
                              description: >-
                                Whether the model is favorited by the
                                authenticated user (null when unauthenticated)
                            thumbnail_url:
                              type: string
                              description: Main thumbnail image URL
                            thumbnail_animated_url:
                              type: string
                              description: Animated thumbnail URL (optional)
                            model_url:
                              type: string
                              description: >-
                                Full model endpoint URL (e.g.,
                                https://fal.run/...)
                            github_url:
                              type: string
                              description: License or GitHub URL (optional)
                            license_type:
                              type: string
                              enum:
                                - commercial
                                - research
                                - private
                              description: License type for the model (optional)
                            date:
                              type: string
                              description: ISO8601 timestamp of model creation
                            group:
                              type: object
                              properties:
                                key:
                                  type: string
                                  description: Group key identifier
                                label:
                                  type: string
                                  description: Human-readable group label
                              required:
                                - key
                                - label
                              description: Model group information (optional)
                            highlighted:
                              type: boolean
                              description: >-
                                Whether the model is highlighted (deprecated,
                                always false)
                              deprecated: true
                              example: false
                            kind:
                              type: string
                              enum:
                                - inference
                                - training
                              description: Model kind - inference or training (optional)
                            training_endpoint_ids:
                              type: array
                              items:
                                type: string
                              description: >-
                                Related training endpoint IDs (optional, only
                                present when non-empty, for inference models)
                            inference_endpoint_ids:
                              type: array
                              items:
                                type: string
                              description: >-
                                Related inference endpoint IDs (optional, only
                                present when non-empty, for training models)
                            stream_url:
                              type: string
                              description: Streaming endpoint URL (optional)
                            duration_estimate:
                              type: number
                              description: Estimated duration in minutes (optional)
                            pinned:
                              type: boolean
                              description: >-
                                Whether the model is pinned (deprecated, always
                                false)
                              deprecated: true
                              example: false
                          required:
                            - display_name
                            - category
                            - description
                            - status
                            - tags
                            - updated_at
                            - is_favorited
                            - thumbnail_url
                            - model_url
                            - date
                            - highlighted
                            - pinned
                          description: >-
                            Model metadata (optional - may be absent for
                            endpoints without registry entries)
                        openapi:
                          anyOf:
                            - type: object
                              properties:
                                openapi:
                                  type: string
                                  description: OpenAPI version (e.g., '3.0.4')
                              required:
                                - openapi
                              additionalProperties: {}
                              description: OpenAPI 3.0 specification for the model
                            - type: object
                              properties:
                                error:
                                  type: object
                                  properties:
                                    code:
                                      type: string
                                      description: Error code (e.g., 'expansion_failed')
                                    message:
                                      type: string
                                      description: Human-readable error message
                                  required:
                                    - code
                                    - message
                                  description: Error details for failed OpenAPI expansion
                              required:
                                - error
                              description: Error encountered while expanding OpenAPI schema
                          description: >-
                            OpenAPI 3.0 specification or error (present when
                            expand=openapi-3.0 is requested)
                        enterprise_status:
                          anyOf:
                            - type: string
                              enum:
                                - ready
                                - pending
                              description: >-
                                'ready' means approved for enterprise use,
                                'pending' means awaiting approval
                            - type: object
                              properties:
                                error:
                                  type: object
                                  properties:
                                    code:
                                      type: string
                                      description: Error code (e.g., 'expansion_failed')
                                    message:
                                      type: string
                                      description: Human-readable error message
                                  required:
                                    - code
                                    - message
                                  description: >-
                                    Error details for failed enterprise status
                                    expansion
                              required:
                                - error
                              description: >-
                                Error encountered while expanding enterprise
                                status
                          description: >-
                            Enterprise readiness status (present when
                            expand=enterprise_status is requested)
                      required:
                        - endpoint_id
                      description: >-
                        Model information with optional metadata and expandable
                        fields
                    description: Array of model information
                  next_cursor:
                    type:
                      - string
                      - 'null'
                    description: Cursor for the next page of results, null if no more pages
                  has_more:
                    type: boolean
                    description: >-
                      Boolean indicating if more results are available
                      (convenience field derived from next_cursor)
                required:
                  - models
                  - has_more
                description: Response containing model data with pagination support
              example:
                models:
                  - endpoint_id: fal-ai/flux/dev
                    metadata:
                      display_name: FLUX.1 [dev]
                      category: text-to-image
                      description: Fast text-to-image generation
                      status: active
                      tags:
                        - fast
                        - pro
                      updated_at: '2025-01-15T12:00:00Z'
                      is_favorited: false
                      thumbnail_url: https://fal.media/files/example.jpg
                      model_url: https://fal.run/fal-ai/flux/dev
                      date: '2024-08-01T00:00:00Z'
                      highlighted: false
                      pinned: false
                next_cursor: null
                has_more: false
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
        '404':
          description: Resource not found
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
                  type: not_found
                  message: Resource not found
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
        - apiKey: []
components:
  securitySchemes:
    apiKey:
      type: apiKey
      in: header
      name: Authorization
      description: >-
        API key must be prefixed with "Key ", e.g. Authorization: Key
        YOUR_API_KEY

````