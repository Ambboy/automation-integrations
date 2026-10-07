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

# fal_client

> API reference for fal_client

```python theme={null}
from fal_client import (
    SyncClient,
    AsyncClient,
    RealtimeConnection,
    AsyncRealtimeConnection,
    Status,
    Queued,
    InProgress,
    Completed,
    FalClientError,
    FalClientHTTPError,
    FalClientTimeoutError,
    StorageACL,
    StorageACLRule,
    StorageSettings,
    SyncRequestHandle,
    AsyncRequestHandle,
    run,
    subscribe_async,
    subscribe,
    submit,
    stream,
    run_async,
    submit_async,
    stream_async,
    realtime,
    realtime_async,
    cancel,
    cancel_async,
    status,
    status_async,
    result,
    result_async,
    encode,
    encode_file,
    encode_image,
    set_get_current_app,
)
```

## Classes

### SyncClient

```python theme={null}
class fal_client.SyncClient
```

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `key` | `Optional[str]` | `None` | - |
  | `default_timeout` | `float` | `120.0` | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `key` | `str \| None` | `None` | - |
  | `default_timeout` | `float` | `120.0` | - |
</Accordion>

<Accordion title="Properties" defaultOpen>
  | Name | Type | Description |
  | :- | :- | :- |
  | `_executor` | `ThreadPoolExecutor` | - |
</Accordion>

<Accordion title="Methods" defaultOpen>
  #### cancel

  ```python theme={null}
  def cancel(self, application: 'str', request_id: 'str') -> 'None'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `request_id` | `str` | - | - |

  **Returns:** `NoneType`

  #### get\_handle

  ```python theme={null}
  def get_handle(self, application: 'str', request_id: 'str') -> 'SyncRequestHandle'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `request_id` | `str` | - | - |

  **Returns:** `SyncRequestHandle`

  #### realtime

  ```python theme={null}
  def realtime(self, application: 'str', *, use_jwt: 'bool' = True, path: 'str' = '/realtime', max_buffering: 'int | None' = None, token_expiration: 'int' = 120, encode_message: 'Callable[[Any], bytes] | None' = None, decode_message: 'Callable[[bytes], Any] | None' = None) -> 'Iterator[RealtimeConnection]'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `use_jwt` | `bool` | `True` | - |
  | `path` | `str` | `'/realtime'` | - |
  | `max_buffering` | `Optional[int]` | `None` | - |
  | `token_expiration` | `int` | `120` | - |
  | `encode_message` | `Optional[Callable[Any, bytes]]` | `None` | - |
  | `decode_message` | `Optional[Callable[bytes, Any]]` | `None` | - |

  **Returns:** `Iterator[RealtimeConnection]`

  #### result

  ```python theme={null}
  def result(self, application: 'str', request_id: 'str') -> 'AnyJSON'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `request_id` | `str` | - | - |

  **Returns:** `dict[str, Any]`

  #### run

  ```python theme={null}
  def run(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', timeout: 'Optional[Union[int, float]]' = None, start_timeout: 'Optional[Union[int, float]]' = None, hint: 'str | None' = None, headers: 'dict[str, str]' = {}) -> 'AnyJSON'
  ```

  Run an application with the given arguments (which will be JSON serialized).

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `arguments` | `dict[str, Any]` | - | - |
  | `path` | `str` | `''` | - |
  | `timeout` | `int \| float \| NoneType` | `None` | Client-side HTTP timeout in seconds. Controls how long the HTTP client waits for a response. Defaults to the client's default\_timeout. |
  | `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts. Does not apply once the application begins processing. |
  | `hint` | `Optional[str]` | `None` | - |
  | `headers` | `dict[str, str]` | `\{\}` | - |

  **Returns:** `dict[str, Any]`

  #### status

  ```python theme={null}
  def status(self, application: 'str', request_id: 'str', *, with_logs: 'bool' = False) -> 'Status'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `request_id` | `str` | - | - |
  | `with_logs` | `bool` | `False` | - |

  **Returns:** `Status`

  #### stream

  ```python theme={null}
  def stream(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '/stream', timeout: 'float | None' = None, headers: 'dict[str, str]' = {}) -> 'Iterator[dict[str, Any]]'
  ```

  Stream the output of an application with the given arguments (which will be JSON serialized). This is only supported at a few select applications at the moment, so be sure to first consult with the documentation of individual applications
  to see if this is supported.

  The function will iterate over each event that is streamed from the server.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `arguments` | `dict[str, Any]` | - | - |
  | `path` | `str` | `'/stream'` | - |
  | `timeout` | `Optional[float]` | `None` | - |
  | `headers` | `dict[str, str]` | `\{\}` | - |

  **Returns:** `Iterator[dict[str, Any]]`

  #### submit

  ```python theme={null}
  def submit(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', hint: 'str | None' = None, webhook_url: 'str | None' = None, priority: 'Optional[Priority]' = None, headers: 'dict[str, str]' = {}, start_timeout: 'Optional[Union[int, float]]' = None) -> 'SyncRequestHandle'
  ```

  Submit an application with the given arguments (which will be JSON serialized).

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `arguments` | `dict[str, Any]` | - | - |
  | `path` | `str` | `''` | - |
  | `hint` | `Optional[str]` | `None` | - |
  | `webhook_url` | `Optional[str]` | `None` | - |
  | `priority` | `Optional[Literal[normal, low]]` | `None` | - |
  | `headers` | `dict[str, str]` | `\{\}` | - |
  | `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts (includes queue wait, retries, and routing). Does not apply once the application begins processing. |

  **Returns:** `SyncRequestHandle`

  #### subscribe

  ```python theme={null}
  def subscribe(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', hint: 'str | None' = None, with_logs: 'bool' = False, interval: 'float' = 0.1, on_enqueue: 'Optional[Callable[[str], None]]' = None, on_queue_update: 'Optional[Callable[[Status], None]]' = None, priority: 'Optional[Priority]' = None, headers: 'dict[str, str]' = {}, start_timeout: 'Optional[Union[int, float]]' = None, client_timeout: 'Optional[Union[int, float]]' = None) -> 'AnyJSON'
  ```

  Subscribe to an application and wait for the result.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `arguments` | `dict[str, Any]` | - | - |
  | `path` | `str` | `''` | - |
  | `hint` | `Optional[str]` | `None` | - |
  | `with_logs` | `bool` | `False` | - |
  | `interval` | `float` | `0.1` | Polling interval in seconds while waiting for request updates. |
  | `on_enqueue` | `Optional[Callable[str, NoneType]]` | `None` | - |
  | `on_queue_update` | `Optional[Callable[Status, NoneType]]` | `None` | - |
  | `priority` | `Optional[Literal[normal, low]]` | `None` | - |
  | `headers` | `dict[str, str]` | `\{\}` | - |
  | `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts (includes queue wait, retries, and routing). Does not apply once the application begins processing. |
  | `client_timeout` | `int \| float \| NoneType` | `None` | Client-side total timeout in seconds. Limits the total time spent waiting for the entire request to complete (including queue wait and processing). If not set, waits indefinitely. |

  **Returns:** `dict[str, Any]`

  #### upload

  ```python theme={null}
  def upload(self, data: 'str | bytes', content_type: 'str', file_name: 'str | None' = None, *, repository: 'UploadRepositoryId | None' = None, fallback_repository: 'UploadRepositoryId | list[UploadRepositoryId] | None' = None, lifecycle: 'StorageSettings | None' = None) -> 'str'
  ```

  Upload the given data blob and return the access URL. The content type should be specified as the second argument. Use
  `upload_file()` or `upload_image()` for convenience. Pass `lifecycle` to
  control uploaded object expiration and initial ACL settings.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `data` | `str \| bytes` | - | - |
  | `content_type` | `str` | - | - |
  | `file_name` | `Optional[str]` | `None` | - |
  | `repository` | `Optional[Literal[fal_v3, cdn, fal]]` | `None` | - |
  | `fallback_repository` | `Literal[fal_v3, cdn, fal] \| list[Literal[fal_v3, cdn, fal]] \| NoneType` | `None` | - |
  | `lifecycle` | `Optional[StorageSettings]` | `None` | - |

  **Returns:** `str`

  #### upload\_file

  ```python theme={null}
  def upload_file(self, path: 'os.PathLike', *, repository: 'UploadRepositoryId | None' = None, fallback_repository: 'UploadRepositoryId | list[UploadRepositoryId] | None' = None, lifecycle: 'StorageSettings | None' = None) -> 'str'
  ```

  Upload a local file and return the access URL. Pass `lifecycle` to control uploaded object expiration and initial ACL
  settings.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `path` | `PathLike` | - | - |
  | `repository` | `Optional[Literal[fal_v3, cdn, fal]]` | `None` | - |
  | `fallback_repository` | `Literal[fal_v3, cdn, fal] \| list[Literal[fal_v3, cdn, fal]] \| NoneType` | `None` | - |
  | `lifecycle` | `Optional[StorageSettings]` | `None` | - |

  **Returns:** `str`

  #### upload\_image

  ```python theme={null}
  def upload_image(self, image: 'Image.Image', format: 'str' = 'jpeg', *, repository: 'UploadRepositoryId | None' = None, fallback_repository: 'UploadRepositoryId | list[UploadRepositoryId] | None' = None, lifecycle: 'StorageSettings | None' = None) -> 'str'
  ```

  Upload a Pillow image object and return the access URL. Pass `lifecycle` to control uploaded object expiration and initial ACL
  settings.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `image` | `Image.Image` | - | - |
  | `format` | `str` | `'jpeg'` | - |
  | `repository` | `UploadRepositoryId \| None` | `None` | - |
  | `fallback_repository` | `UploadRepositoryId \| list[UploadRepositoryId] \| None` | `None` | - |
  | `lifecycle` | `StorageSettings \| None` | `None` | - |

  #### ws\_connect

  ```python theme={null}
  def ws_connect(self, application: 'str', *, use_jwt: 'bool' = True, path: 'str' = '', max_buffering: 'int | None' = None, token_expiration: 'int' = 120) -> "Iterator['Connection']"
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `use_jwt` | `bool` | `True` | - |
  | `path` | `str` | `''` | - |
  | `max_buffering` | `int \| None` | `None` | - |
  | `token_expiration` | `int` | `120` | - |
</Accordion>

### AsyncClient

```python theme={null}
class fal_client.AsyncClient
```

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `key` | `Optional[str]` | `None` | - |
  | `default_timeout` | `float` | `120.0` | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `key` | `str \| None` | `None` | - |
  | `default_timeout` | `float` | `120.0` | - |
</Accordion>

<Accordion title="Methods" defaultOpen>
  #### cancel

  ```python theme={null}
  async def cancel(self, application: 'str', request_id: 'str') -> 'None'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `request_id` | `str` | - | - |

  **Returns:** `NoneType`

  #### get\_handle

  ```python theme={null}
  async def get_handle(self, application: 'str', request_id: 'str') -> 'AsyncRequestHandle'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `request_id` | `str` | - | - |

  **Returns:** `AsyncRequestHandle`

  #### realtime

  ```python theme={null}
  def realtime(self, application: 'str', *, use_jwt: 'bool' = True, path: 'str' = '/realtime', max_buffering: 'int | None' = None, token_expiration: 'int' = 120, encode_message: 'Callable[[Any], bytes] | None' = None, decode_message: 'Callable[[bytes], Any] | None' = None) -> 'AsyncIterator[AsyncRealtimeConnection]'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `use_jwt` | `bool` | `True` | - |
  | `path` | `str` | `'/realtime'` | - |
  | `max_buffering` | `Optional[int]` | `None` | - |
  | `token_expiration` | `int` | `120` | - |
  | `encode_message` | `Optional[Callable[Any, bytes]]` | `None` | - |
  | `decode_message` | `Optional[Callable[bytes, Any]]` | `None` | - |

  **Returns:** `AsyncIterator[AsyncRealtimeConnection]`

  #### result

  ```python theme={null}
  async def result(self, application: 'str', request_id: 'str') -> 'AnyJSON'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `request_id` | `str` | - | - |

  **Returns:** `dict[str, Any]`

  #### run

  ```python theme={null}
  async def run(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', timeout: 'Optional[Union[int, float]]' = None, start_timeout: 'Optional[Union[int, float]]' = None, hint: 'str | None' = None, headers: 'dict[str, str]' = {}) -> 'AnyJSON'
  ```

  Run an application with the given arguments (which will be JSON serialized). The path parameter can be used to specify a subpath when applicable. This method will return the result of the inference call directly.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `arguments` | `dict[str, Any]` | - | - |
  | `path` | `str` | `''` | - |
  | `timeout` | `int \| float \| NoneType` | `None` | Client-side HTTP timeout in seconds. Controls how long the HTTP client waits for a response. Defaults to the client's default\_timeout. |
  | `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts. Does not apply once the application begins processing. |
  | `hint` | `Optional[str]` | `None` | - |
  | `headers` | `dict[str, str]` | `\{\}` | - |

  **Returns:** `dict[str, Any]`

  #### status

  ```python theme={null}
  async def status(self, application: 'str', request_id: 'str', *, with_logs: 'bool' = False) -> 'Status'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `request_id` | `str` | - | - |
  | `with_logs` | `bool` | `False` | - |

  **Returns:** `Status`

  #### stream

  ```python theme={null}
  def stream(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '/stream', timeout: 'float | None' = None, headers: 'dict[str, str]' = {}) -> 'AsyncIterator[dict[str, Any]]'
  ```

  Stream the output of an application with the given arguments (which will be JSON serialized). This is only supported at a few select applications at the moment, so be sure to first consult with the documentation of individual applications
  to see if this is supported.

  The function will iterate over each event that is streamed from the server.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `arguments` | `dict[str, Any]` | - | - |
  | `path` | `str` | `'/stream'` | - |
  | `timeout` | `Optional[float]` | `None` | - |
  | `headers` | `dict[str, str]` | `\{\}` | - |

  **Returns:** `AsyncIterator[dict[str, Any]]`

  #### submit

  ```python theme={null}
  async def submit(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', hint: 'str | None' = None, webhook_url: 'str | None' = None, priority: 'Optional[Priority]' = None, headers: 'dict[str, str]' = {}, start_timeout: 'Optional[Union[int, float]]' = None) -> 'AsyncRequestHandle'
  ```

  Submit an application with the given arguments (which will be JSON serialized). The path parameter can be used to specify a subpath when applicable. This method will return a handle to the request that can be used to check the status
  and retrieve the result of the inference call when it is done.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `arguments` | `dict[str, Any]` | - | - |
  | `path` | `str` | `''` | - |
  | `hint` | `Optional[str]` | `None` | - |
  | `webhook_url` | `Optional[str]` | `None` | - |
  | `priority` | `Optional[Literal[normal, low]]` | `None` | - |
  | `headers` | `dict[str, str]` | `\{\}` | - |
  | `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts (includes queue wait, retries, and routing). Does not apply once the application begins processing. |

  **Returns:** `AsyncRequestHandle`

  #### subscribe

  ```python theme={null}
  async def subscribe(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', hint: 'str | None' = None, with_logs: 'bool' = False, interval: 'float' = 0.1, on_enqueue: 'Optional[Callable[[str], None | Awaitable[None]]]' = None, on_queue_update: 'Optional[Callable[[Status], None | Awaitable[None]]]' = None, priority: 'Optional[Priority]' = None, headers: 'dict[str, str]' = {}, start_timeout: 'Optional[Union[int, float]]' = None, client_timeout: 'Optional[Union[int, float]]' = None) -> 'AnyJSON'
  ```

  Subscribe to an application and wait for the result.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `arguments` | `dict[str, Any]` | - | - |
  | `path` | `str` | `''` | - |
  | `hint` | `Optional[str]` | `None` | - |
  | `with_logs` | `bool` | `False` | - |
  | `interval` | `float` | `0.1` | Polling interval in seconds while waiting for request updates. |
  | `on_enqueue` | `Optional[Callable[str, Optional[Awaitable[NoneType]]]]` | `None` | - |
  | `on_queue_update` | `Optional[Callable[Status, Optional[Awaitable[NoneType]]]]` | `None` | - |
  | `priority` | `Optional[Literal[normal, low]]` | `None` | - |
  | `headers` | `dict[str, str]` | `\{\}` | - |
  | `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts (includes queue wait, retries, and routing). Does not apply once the application begins processing. |
  | `client_timeout` | `int \| float \| NoneType` | `None` | Client-side total timeout in seconds. Limits the total time spent waiting for the entire request to complete (including queue wait and processing). If not set, waits indefinitely. |

  **Returns:** `dict[str, Any]`

  #### upload

  ```python theme={null}
  async def upload(self, data: 'str | bytes', content_type: 'str', file_name: 'str | None' = None, *, repository: 'UploadRepositoryId | None' = None, fallback_repository: 'UploadRepositoryId | list[UploadRepositoryId] | None' = None, lifecycle: 'StorageSettings | None' = None) -> 'str'
  ```

  Upload the given data blob and return the access URL. The content type should be specified as the second argument. Use
  `upload_file()` or `upload_image()` for convenience. Pass `lifecycle` to
  control uploaded object expiration and initial ACL settings.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `data` | `str \| bytes` | - | - |
  | `content_type` | `str` | - | - |
  | `file_name` | `Optional[str]` | `None` | - |
  | `repository` | `Optional[Literal[fal_v3, cdn, fal]]` | `None` | - |
  | `fallback_repository` | `Literal[fal_v3, cdn, fal] \| list[Literal[fal_v3, cdn, fal]] \| NoneType` | `None` | - |
  | `lifecycle` | `Optional[StorageSettings]` | `None` | - |

  **Returns:** `str`

  #### upload\_file

  ```python theme={null}
  async def upload_file(self, path: 'os.PathLike', *, repository: 'UploadRepositoryId | None' = None, fallback_repository: 'UploadRepositoryId | list[UploadRepositoryId] | None' = None, lifecycle: 'StorageSettings | None' = None) -> 'str'
  ```

  Upload a local file and return the access URL. Pass `lifecycle` to control uploaded object expiration and initial ACL
  settings.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `path` | `PathLike` | - | - |
  | `repository` | `Optional[Literal[fal_v3, cdn, fal]]` | `None` | - |
  | `fallback_repository` | `Literal[fal_v3, cdn, fal] \| list[Literal[fal_v3, cdn, fal]] \| NoneType` | `None` | - |
  | `lifecycle` | `Optional[StorageSettings]` | `None` | - |

  **Returns:** `str`

  #### upload\_image

  ```python theme={null}
  async def upload_image(self, image: 'Image.Image', format: 'str' = 'jpeg', *, repository: 'UploadRepositoryId | None' = None, fallback_repository: 'UploadRepositoryId | list[UploadRepositoryId] | None' = None, lifecycle: 'StorageSettings | None' = None) -> 'str'
  ```

  Upload a Pillow image object and return the access URL. Pass `lifecycle` to control uploaded object expiration and initial ACL
  settings.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `image` | `Image.Image` | - | - |
  | `format` | `str` | `'jpeg'` | - |
  | `repository` | `UploadRepositoryId \| None` | `None` | - |
  | `fallback_repository` | `UploadRepositoryId \| list[UploadRepositoryId] \| None` | `None` | - |
  | `lifecycle` | `StorageSettings \| None` | `None` | - |

  #### ws\_connect

  ```python theme={null}
  def ws_connect(self, application: 'str', *, use_jwt: 'bool' = True, path: 'str' = '', max_buffering: 'int | None' = None, token_expiration: 'int' = 120) -> "AsyncIterator['WebSocketClientProtocol']"
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `application` | `str` | - | - |
  | `use_jwt` | `bool` | `True` | - |
  | `path` | `str` | `''` | - |
  | `max_buffering` | `int \| None` | `None` | - |
  | `token_expiration` | `int` | `120` | - |
</Accordion>

### RealtimeConnection

```python theme={null}
class fal_client.RealtimeConnection
```

Synchronous realtime connection wrapper.

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `_ws` | `'Connection'` | - | - |
  | `_encode_message` | `Callable[[Any], bytes] \| None` | `None` | - |
  | `_decode_message` | `Callable[[bytes], Any] \| None` | `None` | - |
</Accordion>

<Accordion title="Methods" defaultOpen>
  #### close

  ```python theme={null}
  def close(self) -> 'None'
  ```

  **Returns:** `NoneType`

  #### recv

  ```python theme={null}
  def recv(self) -> 'dict[str, Any] | None'
  ```

  **Returns:** `Optional[dict[str, Any]]`

  #### send

  ```python theme={null}
  def send(self, arguments: 'dict[str, Any]') -> 'None'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `arguments` | `dict[str, Any]` | - | - |

  **Returns:** `NoneType`
</Accordion>

### AsyncRealtimeConnection

```python theme={null}
class fal_client.AsyncRealtimeConnection
```

Asynchronous realtime connection wrapper.

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `_ws` | `'WebSocketClientProtocol'` | - | - |
  | `_encode_message` | `Callable[[Any], bytes] \| None` | `None` | - |
  | `_decode_message` | `Callable[[bytes], Any] \| None` | `None` | - |
</Accordion>

<Accordion title="Methods" defaultOpen>
  #### close

  ```python theme={null}
  async def close(self) -> 'None'
  ```

  **Returns:** `NoneType`

  #### recv

  ```python theme={null}
  async def recv(self) -> 'dict[str, Any] | None'
  ```

  **Returns:** `Optional[dict[str, Any]]`

  #### send

  ```python theme={null}
  async def send(self, arguments: 'dict[str, Any]') -> 'None'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `arguments` | `dict[str, Any]` | - | - |

  **Returns:** `NoneType`
</Accordion>

### Status

```python theme={null}
class fal_client.Status
```

### Queued

```python theme={null}
class fal_client.Queued
```

Indicates the request is enqueued and waiting to be processed. The position field indicates the relative position in the queue (0-indexed).

> **Inherits from:** `Status`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `position` | `int` | - | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `position` | `int` | - | - |
</Accordion>

### InProgress

```python theme={null}
class fal_client.InProgress
```

Indicates the request is currently being processed. If the status operation called with the `with_logs` parameter set to True, the logs field will be a list of
log objects.

> **Inherits from:** `Status`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `logs` | `Optional[list[dict[str, Any]]]` | - | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `logs` | `list[dict[str, Any]] \| None` | - | - |
</Accordion>

### Completed

```python theme={null}
class fal_client.Completed
```

Indicates the request has been completed and the result can be gathered. The logs field will contain the logs if the status operation was called with the `with_logs` parameter set to True. Metrics
might contain the inference time, and other internal metadata (number of tokens
processed, etc.).

> **Inherits from:** `Status`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `logs` | `Optional[list[dict[str, Any]]]` | - | - |
  | `metrics` | `dict[str, Any]` | - | - |
  | `error` | `Optional[str]` | `None` | - |
  | `error_type` | `Optional[str]` | `None` | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `logs` | `list[dict[str, Any]] \| None` | - | - |
  | `metrics` | `dict[str, Any]` | - | - |
  | `error` | `str \| None` | `None` | - |
  | `error_type` | `str \| None` | `None` | - |
</Accordion>

### FalClientError

```python theme={null}
class fal_client.FalClientError
```

Common base class for all non-exit exceptions.

> **Inherits from:** `Exception`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `args` | - | - | - |
  | `kwargs` | - | - | - |
</Accordion>

### FalClientHTTPError

```python theme={null}
class fal_client.FalClientHTTPError
```

> **Inherits from:** `FalClientError`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `message` | `str` | - | - |
  | `status_code` | `int` | - | - |
  | `response_headers` | `dict[str, str]` | - | - |
  | `response` | `Response` | - | - |
  | `error_type` | `Optional[str]` | `None` | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `message` | `str` | - | - |
  | `status_code` | `int` | - | - |
  | `response_headers` | `dict[str, str]` | - | - |
  | `response` | `httpx.Response` | - | - |
  | `error_type` | `str \| None` | `None` | - |
</Accordion>

### FalClientTimeoutError

```python theme={null}
class fal_client.FalClientTimeoutError
```

> **Inherits from:** `FalClientError`, `TimeoutError`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `timeout` | `float` | - | - |
  | `request_id` | `Optional[str]` | `None` | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `timeout` | `float` | - | - |
  | `request_id` | `Optional[str]` | `None` | - |
</Accordion>

### StorageACL

```python theme={null}
class fal_client.StorageACL
```

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `default` | `Optional[Literal[hide, forbid, allow]]` | `None` | - |
  | `rules` | `Optional[list[StorageACLRule]]` | `None` | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `default` | `StorageACLDecision \| None` | `None` | - |
  | `rules` | `list[StorageACLRule] \| None` | `None` | - |
</Accordion>

### StorageACLRule

```python theme={null}
class fal_client.StorageACLRule
```

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `user` | `str` | - | - |
  | `decision` | `Literal[hide, forbid, allow]` | - | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `user` | `str` | - | - |
  | `decision` | `StorageACLDecision` | - | - |
</Accordion>

### StorageSettings

```python theme={null}
class fal_client.StorageSettings
```

Lifecycle configuration for uploaded files. Use `expires_in="never"` (or omit `expires_in`) to keep the backend's
default retention policy. `expires_in="immediate"` maps to approximately
60 seconds because the backend treats `0` as no expiration.

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `expires_in` | `Literal[never, immediate, 1h, 1d, 7d, 30d, 1y] \| int \| NoneType` | `None` | - |
  | `initial_acl` | `Optional[StorageACL]` | `None` | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `expires_in` | `ObjectExpiration \| None` | `None` | - |
  | `initial_acl` | `StorageACL \| None` | `None` | - |
</Accordion>

### SyncRequestHandle

```python theme={null}
class fal_client.SyncRequestHandle
```

> **Inherits from:** `_BaseRequestHandle`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `request_id` | `str` | - | - |
  | `response_url` | `str` | - | - |
  | `status_url` | `str` | - | - |
  | `cancel_url` | `str` | - | - |
  | `client` | `Client` | - | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `client` | `httpx.Client` | - | - |
</Accordion>

<Accordion title="Methods" defaultOpen>
  #### cancel

  ```python theme={null}
  def cancel(self) -> 'None'
  ```

  Cancel the request.

  **Returns:** `NoneType`

  #### from\_request\_id

  ```python theme={null}
  def from_request_id(cls, client: 'httpx.Client', application: 'str', request_id: 'str') -> 'SyncRequestHandle'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `client` | `Client` | - | - |
  | `application` | `str` | - | - |
  | `request_id` | `str` | - | - |

  **Returns:** `SyncRequestHandle`

  #### get

  ```python theme={null}
  def get(self, *, interval: 'float' = 0.1) -> 'AnyJSON'
  ```

  Wait till the request is completed and return the result of the inference call.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `interval` | `float` | `0.1` | - |

  **Returns:** `dict[str, Any]`

  #### iter\_events

  ```python theme={null}
  def iter_events(self, *, with_logs: 'bool' = False, interval: 'float' = 0.1) -> 'Iterator[Status]'
  ```

  Continuously poll for the status of the request and yield it at each interval till the request is completed. If `with_logs` is True, logs will be included in the response.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `with_logs` | `bool` | `False` | - |
  | `interval` | `float` | `0.1` | - |

  **Returns:** `Iterator[Status]`

  #### status

  ```python theme={null}
  def status(self, *, with_logs: 'bool' = False) -> 'Status'
  ```

  Returns the status of the request (which can be one of the following: Queued, InProgress, Completed). If `with_logs` is True, logs will be included
  for InProgress and Completed statuses.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `with_logs` | `bool` | `False` | - |

  **Returns:** `Status`
</Accordion>

### AsyncRequestHandle

```python theme={null}
class fal_client.AsyncRequestHandle
```

> **Inherits from:** `_BaseRequestHandle`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `request_id` | `str` | - | - |
  | `response_url` | `str` | - | - |
  | `status_url` | `str` | - | - |
  | `cancel_url` | `str` | - | - |
  | `client` | `AsyncClient` | - | - |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name | Type | Default | Description |
  | :- | :- | :- | :- |
  | `client` | `httpx.AsyncClient` | - | - |
</Accordion>

<Accordion title="Methods" defaultOpen>
  #### cancel

  ```python theme={null}
  async def cancel(self) -> 'None'
  ```

  Cancel the request.

  **Returns:** `NoneType`

  #### from\_request\_id

  ```python theme={null}
  def from_request_id(cls, client: 'httpx.AsyncClient', application: 'str', request_id: 'str') -> 'AsyncRequestHandle'
  ```

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `client` | `AsyncClient` | - | - |
  | `application` | `str` | - | - |
  | `request_id` | `str` | - | - |

  **Returns:** `AsyncRequestHandle`

  #### get

  ```python theme={null}
  async def get(self, *, interval: 'float' = 0.1) -> 'AnyJSON'
  ```

  Wait till the request is completed and return the result.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `interval` | `float` | `0.1` | - |

  **Returns:** `dict[str, Any]`

  #### iter\_events

  ```python theme={null}
  def iter_events(self, *, with_logs: 'bool' = False, interval: 'float' = 0.1) -> 'AsyncIterator[Status]'
  ```

  Continuously poll for the status of the request and yield it at each interval till the request is completed. If `with_logs` is True, logs will be included in the response.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `with_logs` | `bool` | `False` | - |
  | `interval` | `float` | `0.1` | - |

  **Returns:** `AsyncIterator[Status]`

  #### status

  ```python theme={null}
  async def status(self, *, with_logs: 'bool' = False) -> 'Status'
  ```

  Returns the status of the request (which can be one of the following: Queued, InProgress, Completed). If `with_logs` is True, logs will be included
  for InProgress and Completed statuses.

  | Parameter | Type | Default | Description |
  | :- | :- | :- | :- |
  | `with_logs` | `bool` | `False` | - |

  **Returns:** `Status`
</Accordion>

***

## Functions

### run

```python theme={null}
def run(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', timeout: 'Optional[Union[int, float]]' = None, start_timeout: 'Optional[Union[int, float]]' = None, hint: 'str | None' = None, headers: 'dict[str, str]' = {}) -> 'AnyJSON'
```

Run an application with the given arguments (which will be JSON serialized).

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `arguments` | `dict[str, Any]` | - | - |
| `path` | `str` | `''` | - |
| `timeout` | `int \| float \| NoneType` | `None` | Client-side HTTP timeout in seconds. Controls how long the HTTP client waits for a response. Defaults to the client's default\_timeout. |
| `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts. Does not apply once the application begins processing. |
| `hint` | `Optional[str]` | `None` | - |
| `headers` | `dict[str, str]` | `\{\}` | - |

**Returns:** `dict[str, Any]`

### subscribe\_async

```python theme={null}
async def subscribe_async(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', hint: 'str | None' = None, with_logs: 'bool' = False, interval: 'float' = 0.1, on_enqueue: 'Optional[Callable[[str], None | Awaitable[None]]]' = None, on_queue_update: 'Optional[Callable[[Status], None | Awaitable[None]]]' = None, priority: 'Optional[Priority]' = None, headers: 'dict[str, str]' = {}, start_timeout: 'Optional[Union[int, float]]' = None, client_timeout: 'Optional[Union[int, float]]' = None) -> 'AnyJSON'
```

Subscribe to an application and wait for the result.

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `arguments` | `dict[str, Any]` | - | - |
| `path` | `str` | `''` | - |
| `hint` | `Optional[str]` | `None` | - |
| `with_logs` | `bool` | `False` | - |
| `interval` | `float` | `0.1` | Polling interval in seconds while waiting for request updates. |
| `on_enqueue` | `Optional[Callable[str, Optional[Awaitable[NoneType]]]]` | `None` | - |
| `on_queue_update` | `Optional[Callable[Status, Optional[Awaitable[NoneType]]]]` | `None` | - |
| `priority` | `Optional[Literal[normal, low]]` | `None` | - |
| `headers` | `dict[str, str]` | `\{\}` | - |
| `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts (includes queue wait, retries, and routing). Does not apply once the application begins processing. |
| `client_timeout` | `int \| float \| NoneType` | `None` | Client-side total timeout in seconds. Limits the total time spent waiting for the entire request to complete (including queue wait and processing). If not set, waits indefinitely. |

**Returns:** `dict[str, Any]`

### subscribe

```python theme={null}
def subscribe(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', hint: 'str | None' = None, with_logs: 'bool' = False, interval: 'float' = 0.1, on_enqueue: 'Optional[Callable[[str], None]]' = None, on_queue_update: 'Optional[Callable[[Status], None]]' = None, priority: 'Optional[Priority]' = None, headers: 'dict[str, str]' = {}, start_timeout: 'Optional[Union[int, float]]' = None, client_timeout: 'Optional[Union[int, float]]' = None) -> 'AnyJSON'
```

Subscribe to an application and wait for the result.

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `arguments` | `dict[str, Any]` | - | - |
| `path` | `str` | `''` | - |
| `hint` | `Optional[str]` | `None` | - |
| `with_logs` | `bool` | `False` | - |
| `interval` | `float` | `0.1` | Polling interval in seconds while waiting for request updates. |
| `on_enqueue` | `Optional[Callable[str, NoneType]]` | `None` | - |
| `on_queue_update` | `Optional[Callable[Status, NoneType]]` | `None` | - |
| `priority` | `Optional[Literal[normal, low]]` | `None` | - |
| `headers` | `dict[str, str]` | `\{\}` | - |
| `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts (includes queue wait, retries, and routing). Does not apply once the application begins processing. |
| `client_timeout` | `int \| float \| NoneType` | `None` | Client-side total timeout in seconds. Limits the total time spent waiting for the entire request to complete (including queue wait and processing). If not set, waits indefinitely. |

**Returns:** `dict[str, Any]`

### submit

```python theme={null}
def submit(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', hint: 'str | None' = None, webhook_url: 'str | None' = None, priority: 'Optional[Priority]' = None, headers: 'dict[str, str]' = {}, start_timeout: 'Optional[Union[int, float]]' = None) -> 'SyncRequestHandle'
```

Submit an application with the given arguments (which will be JSON serialized).

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `arguments` | `dict[str, Any]` | - | - |
| `path` | `str` | `''` | - |
| `hint` | `Optional[str]` | `None` | - |
| `webhook_url` | `Optional[str]` | `None` | - |
| `priority` | `Optional[Literal[normal, low]]` | `None` | - |
| `headers` | `dict[str, str]` | `\{\}` | - |
| `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts (includes queue wait, retries, and routing). Does not apply once the application begins processing. |

**Returns:** `SyncRequestHandle`

### stream

```python theme={null}
def stream(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '/stream', timeout: 'float | None' = None, headers: 'dict[str, str]' = {}) -> 'Iterator[dict[str, Any]]'
```

Stream the output of an application with the given arguments (which will be JSON serialized). This is only supported at a few select applications at the moment, so be sure to first consult with the documentation of individual applications
to see if this is supported.

The function will iterate over each event that is streamed from the server.

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `arguments` | `dict[str, Any]` | - | - |
| `path` | `str` | `'/stream'` | - |
| `timeout` | `Optional[float]` | `None` | - |
| `headers` | `dict[str, str]` | `\{\}` | - |

**Returns:** `Iterator[dict[str, Any]]`

### run\_async

```python theme={null}
async def run_async(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', timeout: 'Optional[Union[int, float]]' = None, start_timeout: 'Optional[Union[int, float]]' = None, hint: 'str | None' = None, headers: 'dict[str, str]' = {}) -> 'AnyJSON'
```

Run an application with the given arguments (which will be JSON serialized). The path parameter can be used to specify a subpath when applicable. This method will return the result of the inference call directly.

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `arguments` | `dict[str, Any]` | - | - |
| `path` | `str` | `''` | - |
| `timeout` | `int \| float \| NoneType` | `None` | Client-side HTTP timeout in seconds. Controls how long the HTTP client waits for a response. Defaults to the client's default\_timeout. |
| `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts. Does not apply once the application begins processing. |
| `hint` | `Optional[str]` | `None` | - |
| `headers` | `dict[str, str]` | `\{\}` | - |

**Returns:** `dict[str, Any]`

### submit\_async

```python theme={null}
async def submit_async(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '', hint: 'str | None' = None, webhook_url: 'str | None' = None, priority: 'Optional[Priority]' = None, headers: 'dict[str, str]' = {}, start_timeout: 'Optional[Union[int, float]]' = None) -> 'AsyncRequestHandle'
```

Submit an application with the given arguments (which will be JSON serialized). The path parameter can be used to specify a subpath when applicable. This method will return a handle to the request that can be used to check the status
and retrieve the result of the inference call when it is done.

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `arguments` | `dict[str, Any]` | - | - |
| `path` | `str` | `''` | - |
| `hint` | `Optional[str]` | `None` | - |
| `webhook_url` | `Optional[str]` | `None` | - |
| `priority` | `Optional[Literal[normal, low]]` | `None` | - |
| `headers` | `dict[str, str]` | `\{\}` | - |
| `start_timeout` | `int \| float \| NoneType` | `None` | Server-side request timeout in seconds. Limits total time spent waiting before processing starts (includes queue wait, retries, and routing). Does not apply once the application begins processing. |

**Returns:** `AsyncRequestHandle`

### stream\_async

```python theme={null}
def stream_async(self, application: 'str', arguments: 'AnyJSON', *, path: 'str' = '/stream', timeout: 'float | None' = None, headers: 'dict[str, str]' = {}) -> 'AsyncIterator[dict[str, Any]]'
```

Stream the output of an application with the given arguments (which will be JSON serialized). This is only supported at a few select applications at the moment, so be sure to first consult with the documentation of individual applications
to see if this is supported.

The function will iterate over each event that is streamed from the server.

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `arguments` | `dict[str, Any]` | - | - |
| `path` | `str` | `'/stream'` | - |
| `timeout` | `Optional[float]` | `None` | - |
| `headers` | `dict[str, str]` | `\{\}` | - |

**Returns:** `AsyncIterator[dict[str, Any]]`

### realtime

```python theme={null}
def realtime(self, application: 'str', *, use_jwt: 'bool' = True, path: 'str' = '/realtime', max_buffering: 'int | None' = None, token_expiration: 'int' = 120, encode_message: 'Callable[[Any], bytes] | None' = None, decode_message: 'Callable[[bytes], Any] | None' = None) -> 'Iterator[RealtimeConnection]'
```

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `use_jwt` | `bool` | `True` | - |
| `path` | `str` | `'/realtime'` | - |
| `max_buffering` | `Optional[int]` | `None` | - |
| `token_expiration` | `int` | `120` | - |
| `encode_message` | `Optional[Callable[Any, bytes]]` | `None` | - |
| `decode_message` | `Optional[Callable[bytes, Any]]` | `None` | - |

**Returns:** `Iterator[RealtimeConnection]`

### realtime\_async

```python theme={null}
def realtime_async(self, application: 'str', *, use_jwt: 'bool' = True, path: 'str' = '/realtime', max_buffering: 'int | None' = None, token_expiration: 'int' = 120, encode_message: 'Callable[[Any], bytes] | None' = None, decode_message: 'Callable[[bytes], Any] | None' = None) -> 'AsyncIterator[AsyncRealtimeConnection]'
```

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `use_jwt` | `bool` | `True` | - |
| `path` | `str` | `'/realtime'` | - |
| `max_buffering` | `Optional[int]` | `None` | - |
| `token_expiration` | `int` | `120` | - |
| `encode_message` | `Optional[Callable[Any, bytes]]` | `None` | - |
| `decode_message` | `Optional[Callable[bytes, Any]]` | `None` | - |

**Returns:** `AsyncIterator[AsyncRealtimeConnection]`

### cancel

```python theme={null}
def cancel(self, application: 'str', request_id: 'str') -> 'None'
```

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `request_id` | `str` | - | - |

**Returns:** `NoneType`

### cancel\_async

```python theme={null}
async def cancel_async(self, application: 'str', request_id: 'str') -> 'None'
```

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `request_id` | `str` | - | - |

**Returns:** `NoneType`

### status

```python theme={null}
def status(self, application: 'str', request_id: 'str', *, with_logs: 'bool' = False) -> 'Status'
```

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `request_id` | `str` | - | - |
| `with_logs` | `bool` | `False` | - |

**Returns:** `Status`

### status\_async

```python theme={null}
async def status_async(self, application: 'str', request_id: 'str', *, with_logs: 'bool' = False) -> 'Status'
```

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `request_id` | `str` | - | - |
| `with_logs` | `bool` | `False` | - |

**Returns:** `Status`

### result

```python theme={null}
def result(self, application: 'str', request_id: 'str') -> 'AnyJSON'
```

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `request_id` | `str` | - | - |

**Returns:** `dict[str, Any]`

### result\_async

```python theme={null}
async def result_async(self, application: 'str', request_id: 'str') -> 'AnyJSON'
```

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `application` | `str` | - | - |
| `request_id` | `str` | - | - |

**Returns:** `dict[str, Any]`

### encode

```python theme={null}
def encode(data: 'str | bytes', content_type: 'str') -> 'str'
```

Encode the given data blob to a data URL with the specified content type.

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `data` | `str \| bytes` | - | - |
| `content_type` | `str` | - | - |

**Returns:** `str`

### encode\_file

```python theme={null}
def encode_file(path: 'os.PathLike') -> 'str'
```

Encode a file from the local filesystem to a data URL with the inferred content type.

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `path` | `PathLike` | - | - |

**Returns:** `str`

### encode\_image

```python theme={null}
def encode_image(image: 'Image.Image', format: 'str' = 'jpeg') -> 'str'
```

Encode a pillow image object to a data URL with the specified format.

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `image` | `Image.Image` | - | - |
| `format` | `str` | `'jpeg'` | - |

### set\_get\_current\_app

```python theme={null}
def set_get_current_app(func: 'Callable[[], Any]')
```

| Parameter | Type | Default | Description |
| :- | :- | :- | :- |
| `func` | `Callable[Any]` | - | - |
