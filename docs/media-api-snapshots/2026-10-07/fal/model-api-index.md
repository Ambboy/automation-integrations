# fal: Model API Reference

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

## Model API Reference

- [Model API Reference](https://fal.ai/docs/model-api-reference/index.md): Complete API reference for fal.ai's image, video, audio, vision, and 3D generation models on fal.ai.

### Video Generation

- [Video Generation API](https://fal.ai/docs/model-api-reference/video-generation-api/overview.md): Video Generation API reference. Generate videos from text prompts or images using cutting-edge video generation models.

#### Birefnet

- [Birefnet V2 API](https://fal.ai/docs/model-api-reference/video-generation-api/birefnet-v2.md): API reference for Birefnet V2. Video background removal version of bilateral reference framework (BiRefNet) for high-resolution dichotomous image segmentation (DIS)

#### Bria

- [Bria Video API](https://fal.ai/docs/model-api-reference/video-generation-api/bria-video.md): API reference for Bria Video. Automatically remove backgrounds from videos -perfect for creating clean, professional content without a green screen.

#### Bytedance

- [Bytedance Dreamactor API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-dreamactor.md): API reference for Bytedance Dreamactor. Transfer motion from a video to characters in an image using Dreamactor v2. Great performance for non-human and multiple characters
- [Bytedance Omnihuman API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-omnihuman.md): API reference for Bytedance Omnihuman. OmniHuman generates video using an image of a human figure paired with an audio file. It produces vivid, high-quality videos where the character’s emotions and m
- [Bytedance Video Stylize API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-video-stylize.md): API reference for Bytedance Video Stylize. Transform your images into stylized videos using this workflow.

##### Seedance

###### V1

- [Bytedance Seedance V1 Lite API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-seedance-v1-lite.md): API reference for Bytedance Seedance V1 Lite. Seedance 1.0 Lite

###### Pro

- [Bytedance Seedance V1 Pro Fast API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-seedance-v1-pro-fast.md): API reference for Bytedance Seedance V1 Pro Fast. Image to Video endpoint for Seedance 1.0 Pro Fast, a next-generation video model designed to deliver maximum performance at minimal cost
- [Bytedance Seedance V1 Pro Image To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-seedance-v1-pro-image-to-video.md): API reference for Bytedance Seedance V1 Pro Image To Video. Seedance 1.0 Pro, a high quality video generation model developed by Bytedance.
- [Bytedance Seedance V1 Pro Text To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-seedance-v1-pro-text-to-video.md): API reference for Bytedance Seedance V1 Pro Text To Video. Seedance 1.0 Pro, a high quality video generation model developed by Bytedance.

###### V1.5

- [Bytedance Seedance V1.5 Pro API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-seedance-v1.5-pro.md): API reference for Bytedance Seedance V1.5 Pro. Generate videos with audio with Seedance 1.5 (supports start & end frame)

##### Seedance 2.0

- [Bytedance Seedance 2.0 Fast API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-seedance-2.0-fast.md): API reference for Bytedance Seedance 2.0 Fast. ByteDance's most advanced text-to-video model, fast tier. Lower latency and cost with cinematic output, native audio, multi-shot editing, and director-le
- [Bytedance Seedance 2.0 Image To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-seedance-2.0-image-to-video.md): API reference for Bytedance Seedance 2.0 Image To Video. ByteDance's most advanced image-to-video model. Animate still images into cinematic video with synchronized audio, start and end frame control,
- [Bytedance Seedance 2.0 Reference To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-seedance-2.0-reference-to-video.md): API reference for Bytedance Seedance 2.0 Reference To Video. ByteDance's most advanced reference-to-video model. Generate video from up to 9 images, 3 videos, and 3 audio clips with native audio and c
- [Bytedance Seedance 2.0 Text To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/bytedance-seedance-2.0-text-to-video.md): API reference for Bytedance Seedance 2.0 Text To Video. ByteDance's most advanced text-to-video model. Cinematic output with native audio, multi-shot editing, real-world physics, and director-level ca

#### Kling Video

- [Kling Video Lipsync API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-lipsync.md): API reference for Kling Video Lipsync. Kling LipSync is an audio-to-video model that generates realistic lip movements from audio input.

##### Ai Avatar

- [Kling Video Ai Avatar V2 API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-ai-avatar-v2.md): API reference for Kling Video Ai Avatar V2. Kling AI Avatar v2 Pro: The premium endpoint for creating avatar videos with realistic humans, animals, cartoons, or stylized characters

##### O1

- [Kling Video O1 Image To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o1-image-to-video.md): API reference for Kling Video O1 Image To Video. Generate a video by taking a start frame and an end frame, animating the transition between them while following text-driven style and scene guidance.
- [Kling Video O1 Reference To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o1-reference-to-video.md): API reference for Kling Video O1 Reference To Video. Transform images, elements, and text into consistent, high-quality video scenes, ensuring stable character identity, object details, and environmen
- [Kling Video O1 Video To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o1-video-to-video.md): API reference for Kling Video O1 Video To Video. Edit an existing video using natural-language instructions, transforming subjects, settings, and style while retaining the original motion structure.

###### Standard

- [Kling Video O1 Standard Image To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o1-standard-image-to-video.md): API reference for Kling Video O1 Standard Image To Video. Generate a video by taking a start frame and an end frame, animating the transition between them while following text-driven style and scene g
- [Kling Video O1 Standard Reference To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o1-standard-reference-to-video.md): API reference for Kling Video O1 Standard Reference To Video. Transform images, elements, and text into consistent, high-quality video scenes, ensuring stable character identity, object details, and e
- [Kling Video O1 Standard Video To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o1-standard-video-to-video.md): API reference for Kling Video O1 Standard Video To Video. Edit an existing video using natural-language instructions, transforming subjects, settings, and style while retaining the original motion str

##### O3

###### Pro

- [Kling Video O3 Pro Image To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o3-pro-image-to-video.md): API reference for Kling Video O3 Pro Image To Video. Generate a video by taking a start frame and an end frame, animating the transition between them while following text-driven style and scene guidan
- [Kling Video O3 Pro Reference To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o3-pro-reference-to-video.md): API reference for Kling Video O3 Pro Reference To Video. Transform images, elements, and text into consistent, high-quality video scenes, ensuring stable character identity, object details, and enviro
- [Kling Video O3 Pro Text To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o3-pro-text-to-video.md): API reference for Kling Video O3 Pro Text To Video. Generate realistic videos using Kling O3 from Kling Team!
- [Kling Video O3 Pro Video To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o3-pro-video-to-video.md): API reference for Kling Video O3 Pro Video To Video. Edit videos using Kling O3 from Kling Team!

###### Standard

- [Kling Video O3 Standard Image To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o3-standard-image-to-video.md): API reference for Kling Video O3 Standard Image To Video. Generate a video by taking a start frame and an end frame, animating the transition between them while following text-driven style and scene g
- [Kling Video O3 Standard Reference To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o3-standard-reference-to-video.md): API reference for Kling Video O3 Standard Reference To Video. Transform images, elements, and text into consistent, high-quality video scenes, ensuring stable character identity, object details, and e
- [Kling Video O3 Standard Text To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o3-standard-text-to-video.md): API reference for Kling Video O3 Standard Text To Video. Generate realistic videos using Kling O3 from Kling Team!
- [Kling Video O3 Standard Video To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o3-standard-video-to-video.md): API reference for Kling Video O3 Standard Video To Video. Edit videos using Kling O3 from Kling Team!

##### V1

- [Kling Video V1 Pro API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v1-pro.md): API reference for Kling Video V1 Pro. Kling AI Avatar Pro: The premium endpoint for creating avatar videos with realistic humans, animals, cartoons, or stylized characters
- [Kling Video V1 Standard API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v1-standard.md): API reference for Kling Video V1 Standard. Generate video clips from your images using Kling 1.0

##### V1.5

- [Kling Video V1.5 Pro API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v1.5-pro.md): API reference for Kling Video V1.5 Pro. Generate video clips from your images using Kling 1.5 (pro)

##### V1.6

- [Kling Video V1.6 Pro API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v1.6-pro.md): API reference for Kling Video V1.6 Pro. Generate video clips from your images using Kling 1.6 (pro)
- [Kling Video V1.6 Standard API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v1.6-standard.md): API reference for Kling Video V1.6 Standard. Generate video clips from your images using Kling 1.6 (std)

##### V2

- [Kling Video V2 Master API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v2-master.md): API reference for Kling Video V2 Master. Generate video clips from your images using Kling 2.0 Master

##### V2.1

- [Kling Video V2.1 Master API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v2.1-master.md): API reference for Kling Video V2.1 Master. Kling 2.1 Master: The premium endpoint for Kling 2.1, designed for top-tier image-to-video generation with unparalleled motion fluidity, cinematic visuals, a
- [Kling Video V2.1 Pro API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v2.1-pro.md): API reference for Kling Video V2.1 Pro. Kling 2.1 Pro is an advanced endpoint for the Kling 2.1 model, offering professional-grade videos with enhanced visual fidelity, precise camera movements, and d
- [Kling Video V2.1 Standard API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v2.1-standard.md): API reference for Kling Video V2.1 Standard. Kling 2.1 Standard is a cost-efficient endpoint for the Kling 2.1 model, delivering high-quality image-to-video generation

##### V2.5 Turbo

- [Kling Video V2.5 Turbo Pro API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v2.5-turbo-pro.md): API reference for Kling Video V2.5 Turbo Pro. Kling 2.5 Turbo Pro: Top-tier image-to-video generation with unparalleled motion fluidity, cinematic visuals, and exceptional prompt precision.
- [Kling Video V2.5 Turbo Standard API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v2.5-turbo-standard.md): API reference for Kling Video V2.5 Turbo Standard. Kling 2.5 Turbo Standard: Top-tier image-to-video generation with unparalleled motion fluidity, cinematic visuals, and exceptional prompt precision.

##### V2.6

- [Kling Video V2.6 Pro API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v2.6-pro.md): API reference for Kling Video V2.6 Pro. Kling 2.6 Pro: Top-tier image-to-video with cinematic visuals, fluid motion, and native audio generation.
- [Kling Video V2.6 Standard API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v2.6-standard.md): API reference for Kling Video V2.6 Standard. Transfer movements from a reference video to any character image. Cost-effective mode for motion transfer, perfect for portraits and simple animations.

##### V3

- [Kling Video V3 Pro API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v3-pro.md): API reference for Kling Video V3 Pro. Kling 3.0 Pro: Top-tier text-to-video with cinematic visuals, fluid motion, and native audio generation, with multi-shot support.
- [Kling Video V3 Standard API](https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v3-standard.md): API reference for Kling Video V3 Standard. Kling 3.0 Standard: Top-tier image-to-video with cinematic visuals, fluid motion, and native audio generation, with custom element support.

#### Seedvr

- [Seedvr Upscale API](https://fal.ai/docs/model-api-reference/video-generation-api/seedvr-upscale.md): API reference for Seedvr Upscale. Upscale your videos using SeedVR2 with temporal consistency!

#### Sora 2

- [Sora 2 Characters API](https://fal.ai/docs/model-api-reference/video-generation-api/sora-2-characters.md): API reference for Sora 2 Characters. Generate character ids to use with Sora 2 generations
- [Sora 2 Image To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/sora-2-image-to-video.md): API reference for Sora 2 Image To Video. Image-to-video endpoint for Sora 2, OpenAI's state-of-the-art video model capable of creating richly detailed, dynamic clips with audio from natural language o
- [Sora 2 Text To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/sora-2-text-to-video.md): API reference for Sora 2 Text To Video. Text-to-video endpoint for Sora 2, OpenAI's state-of-the-art video model capable of creating richly detailed, dynamic clips with audio from natural language or
- [Sora 2 Video To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/sora-2-video-to-video.md): API reference for Sora 2 Video To Video. Video-to-video remix endpoint for Sora 2, OpenAI’s advanced model that transforms existing videos based on new text or image prompts allowing rich edits, style

#### Topaz

- [Topaz Upscale API](https://fal.ai/docs/model-api-reference/video-generation-api/topaz-upscale.md): API reference for Topaz Upscale. Professional-grade video upscaling using Topaz technology. Enhance your videos with high-quality upscaling.

#### Veo3.1

- [Veo3.1 API](https://fal.ai/docs/model-api-reference/video-generation-api/veo3.1.md): API reference for Veo3.1. Veo 3.1 by Google, the most advanced AI video generation model in the world. With sound on!
- [Veo3.1 Extend Video API](https://fal.ai/docs/model-api-reference/video-generation-api/veo3.1-extend-video.md): API reference for Veo3.1 Extend Video. Extend Veo-Created Videos up to 30 seconds
- [Veo3.1 Fast API](https://fal.ai/docs/model-api-reference/video-generation-api/veo3.1-fast.md): API reference for Veo3.1 Fast. Faster and more cost effective version of Google's Veo 3.1!
- [Veo3.1 First Last Frame To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/veo3.1-first-last-frame-to-video.md): API reference for Veo3.1 First Last Frame To Video. Generate videos from a first and last framed using Google's Veo 3.1
- [Veo3.1 Image To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/veo3.1-image-to-video.md): API reference for Veo3.1 Image To Video. Veo 3.1 is the latest state-of-the art video generation model from Google DeepMind
- [Veo3.1 Lite API](https://fal.ai/docs/model-api-reference/video-generation-api/veo3.1-lite.md): API reference for Veo3.1 Lite. Veo 3.1 Lite balances practical utility with professional capabilities, supporting Text-to-Video and Image-to-Video
- [Veo3.1 Reference To Video API](https://fal.ai/docs/model-api-reference/video-generation-api/veo3.1-reference-to-video.md): API reference for Veo3.1 Reference To Video. Generate Videos from images using Google's Veo 3.1

#### Xai

- [Xai Grok Imagine Video API](https://fal.ai/docs/model-api-reference/video-generation-api/xai-grok-imagine-video.md): API reference for Xai Grok Imagine Video. Generate videos from images with audio using xAI's Grok Imagine Video model.

### Image Generation

- [Image Generation API](https://fal.ai/docs/model-api-reference/image-generation-api/overview.md): Image Generation API reference. Generate and edit images using state-of-the-art diffusion and transformer models.
- [Birefnet API](https://fal.ai/docs/model-api-reference/image-generation-api/birefnet.md): API reference for Birefnet. bilateral reference framework (BiRefNet) for high-resolution dichotomous image segmentation (DIS)
- [Florence 2 Large API](https://fal.ai/docs/model-api-reference/image-generation-api/florence-2-large.md): API reference for Florence 2 Large. Florence-2 is an advanced vision foundation model that uses a prompt-based approach to handle a wide range of vision and vision-language tasks
- [Flux 2 Pro API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-2-pro.md): API reference for Flux 2 Pro. Image editing with FLUX.2 [pro] from Black Forest Labs. Ideal for high-quality image manipulation, style transfer, and sequential editing workflows
- [Flux Lora API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-lora.md): API reference for Flux Lora. Super fast endpoint for the FLUX.1 [dev] model with LoRA support, enabling rapid and high-quality image generation using pre-trained LoRA adaptations for personalization,
- [Gemini 3 Pro Image Preview API](https://fal.ai/docs/model-api-reference/image-generation-api/gemini-3-pro-image-preview.md): API reference for Gemini 3 Pro Image Preview. Gemini 3 Pro Image (a.k.a Nano Banana Pro) is Google's state-of-the-art high-fidelity image generation and editing model
- [Gpt Image 1.5 API](https://fal.ai/docs/model-api-reference/image-generation-api/gpt-image-1.5.md): API reference for Gpt Image 1.5. GPT Image 1.5 generates high-fidelity images with strong prompt adherence, preserving composition, lighting, and fine-grained detail.
- [Imageutils API](https://fal.ai/docs/model-api-reference/image-generation-api/imageutils.md): API reference for Imageutils. Remove the background from an image.
- [Nano Banana API](https://fal.ai/docs/model-api-reference/image-generation-api/nano-banana.md): API reference for Nano Banana. Google's famous original image generation and editing model
- [Nano Banana 2 API](https://fal.ai/docs/model-api-reference/image-generation-api/nano-banana-2.md): API reference for Nano Banana 2. Nano Banana 2 is Google's new state-of-the-art fast image generation and editing model
- [Nano Banana Pro API](https://fal.ai/docs/model-api-reference/image-generation-api/nano-banana-pro.md): API reference for Nano Banana Pro. Nano Banana Pro is Google's new state-of-the-art image generation and editing model

#### Bria

- [Bria Background API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-background.md): API reference for Bria Background. Bria RMBG 2.0 enables seamless removal of backgrounds from images, ideal for professional editing tasks. Trained exclusively on licensed data for safe and risk-free
- [Bria Embed Product API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-embed-product.md): API reference for Bria Embed Product. Seamlessly integrate one or more products into a predefined scene with pixel-perfect control.
- [Bria Eraser API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-eraser.md): API reference for Bria Eraser. Bria Eraser enables precise removal of unwanted objects from images while maintaining high-quality outputs. Trained exclusively on licensed data for safe and risk-free c
- [Bria Expand API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-expand.md): API reference for Bria Expand. Bria Expand expands images beyond their borders in high quality. Trained exclusively on licensed data for safe and risk-free commercial use. Access the model's source co
- [Bria Fibo API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-fibo.md): API reference for Bria Fibo. SOTA Open source model trained on licensed data, transforming intent into structured control for precise, high-quality AI image generation in enterprise and agentic workfl
- [Bria Fibo Edit API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-fibo-edit.md): API reference for Bria Fibo Edit. A high-quality editing model that achieves maximum controllability and transparency by combining JSON + Mask + Image.
- [Bria Fibo Lite API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-fibo-lite.md): API reference for Bria Fibo Lite. Fibo Lite, the new addition to the Fibo model family, allows generating high-quality images with the same controllability of the JSON structured prompt with significa
- [Bria Genfill API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-genfill.md): API reference for Bria Genfill. Bria GenFill enables high-quality object addition or visual transformation. Trained exclusively on licensed data for safe and risk-free commercial use. Access the model
- [Bria Product Shot API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-product-shot.md): API reference for Bria Product Shot. Place any product in any scenery with just a prompt or reference image while maintaining high integrity of the product. Trained exclusively on licensed data for sa
- [Bria Reimagine API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-reimagine.md): API reference for Bria Reimagine. Structure Reference allows generating new images while preserving the structure of an input image, guided by text prompts. Perfect for transforming sketches, illustra
- [Bria Replace Background API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-replace-background.md): API reference for Bria Replace Background. Creates enriched product shots by placing them in various environments using textual descriptions.
- [Bria Text To Image API](https://fal.ai/docs/model-api-reference/image-generation-api/bria-text-to-image.md): API reference for Bria Text To Image. Bria's Text-to-Image model for HD images. Trained exclusively on licensed data for safe and risk-free commercial use. Available also as source code and weights. F

#### Bytedance

##### Dreamina

- [Bytedance Dreamina V3.1 API](https://fal.ai/docs/model-api-reference/image-generation-api/bytedance-dreamina-v3.1.md): API reference for Bytedance Dreamina V3.1. Dreamina showcases superior picture effects, with significant improvements in picture aesthetics, precise and diverse styles, and rich details.

##### Seedream

- [Bytedance Seedream V3 API](https://fal.ai/docs/model-api-reference/image-generation-api/bytedance-seedream-v3.md): API reference for Bytedance Seedream V3. Seedream 3.0 is a bilingual (Chinese and English) text-to-image model that excels at text-to-image generation.
- [Bytedance Seedream V4 API](https://fal.ai/docs/model-api-reference/image-generation-api/bytedance-seedream-v4.md): API reference for Bytedance Seedream V4. A new-generation image creation model ByteDance, Seedream 4.0 integrates image generation and image editing capabilities into a single, unified architecture.
- [Bytedance Seedream V4.5 API](https://fal.ai/docs/model-api-reference/image-generation-api/bytedance-seedream-v4.5.md): API reference for Bytedance Seedream V4.5. A new-generation image creation model ByteDance, Seedream 4.5 integrates image generation and image editing capabilities into a single, unified architecture.

###### V5

- [Bytedance Seedream V5 Lite API](https://fal.ai/docs/model-api-reference/image-generation-api/bytedance-seedream-v5-lite.md): API reference for Bytedance Seedream V5 Lite. Image editing endpoint for the fast Lite version of Seedream 5.0, supporting high quality intelligent image editing with multiple inputs.

#### Flux

- [Flux Dev API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-dev.md): API reference for Flux Dev. FLUX.1 [dev] is a 12 billion parameter flow transformer that generates high-quality images from text. It is suitable for personal and commercial use.
- [Flux Krea API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-krea.md): API reference for Flux Krea. FLUX.1 Krea [dev] is a 12 billion parameter flow transformer that generates high-quality images from text with incredible aesthetics. It is suitable for personal and comme
- [Flux Schnell API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-schnell.md): API reference for Flux Schnell. FLUX.1 [schnell] is a 12 billion parameter flow transformer that generates high-quality images from text in 1 to 4 steps, suitable for personal and commercial use.
- [Flux Srpo API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-srpo.md): API reference for Flux Srpo. FLUX.1 SRPO [dev] is a 12 billion parameter flow transformer that generates high-quality images from text with incredible aesthetics. It is suitable for personal and comme

#### Flux Pro

- [Flux Pro V1 API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-pro-v1.md): API reference for Flux Pro V1. FLUX.1 [pro] Fill is a high-performance endpoint for the FLUX.1 [pro] model that enables rapid transformation of existing images, delivering high-quality style transfers
- [Flux Pro V1.1 API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-pro-v1.1.md): API reference for Flux Pro V1.1. FLUX1.1 [pro] is an enhanced version of FLUX.1 [pro], improved image generation capabilities, delivering superior composition, detail, and artistic fidelity compared t
- [Flux Pro V1.1 Ultra API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-pro-v1.1-ultra.md): API reference for Flux Pro V1.1 Ultra. FLUX1.1 [pro] ultra is the newest version of FLUX1.1 [pro], maintaining professional-grade image quality while delivering up to 2K resolution with improved photo
- [Flux Pro V1.1 Ultra Finetuned API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-pro-v1.1-ultra-finetuned.md): API reference for Flux Pro V1.1 Ultra Finetuned. FLUX1.1 [pro] ultra fine-tuned is the newest version of FLUX1.1 [pro] with a fine-tuned LoRA, maintaining professional-grade image quality while delive

##### Kontext

- [Flux Pro Kontext API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-pro-kontext.md): API reference for Flux Pro Kontext. FLUX.1 Kontext [pro] handles both text and reference images as inputs, seamlessly enabling targeted, local edits and complex transformations of entire scenes.
- [Flux Pro Kontext Max API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-pro-kontext-max.md): API reference for Flux Pro Kontext Max. FLUX.1 Kontext [max] is a model with greatly improved prompt adherence and typography generation meet premium consistency for editing without compromise on spee
- [Flux Pro Kontext Multi API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-pro-kontext-multi.md): API reference for Flux Pro Kontext Multi. Experimental version of FLUX.1 Kontext [pro] with multi image handling capabilities
- [Flux Pro Kontext Text To Image API](https://fal.ai/docs/model-api-reference/image-generation-api/flux-pro-kontext-text-to-image.md): API reference for Flux Pro Kontext Text To Image. The FLUX.1 Kontext [pro] text-to-image delivers state-of-the-art image generation results with unprecedented prompt following, photorealistic renderin

#### Ideogram

- [Ideogram Character API](https://fal.ai/docs/model-api-reference/image-generation-api/ideogram-character.md): API reference for Ideogram Character. Generate consistent character appearances across multiple images. Maintain facial features, proportions, and distinctive traits for cohesive storytelling and bran
- [Ideogram Upscale API](https://fal.ai/docs/model-api-reference/image-generation-api/ideogram-upscale.md): API reference for Ideogram Upscale. Ideogram Upscale enhances the resolution of the reference image by up to 2X and might enhance the reference image too. Optionally refine outputs with a prompt for g
- [Ideogram V3 API](https://fal.ai/docs/model-api-reference/image-generation-api/ideogram-v3.md): API reference for Ideogram V3. Generate high-quality images, posters, and logos with Ideogram V3. Features exceptional typography handling and realistic outputs optimized for commercial and creative u

##### V2

- [Ideogram V2 API](https://fal.ai/docs/model-api-reference/image-generation-api/ideogram-v2.md): API reference for Ideogram V2. Generate high-quality images, posters, and logos with Ideogram V2. Features exceptional typography handling and realistic outputs optimized for commercial and creative u
- [Ideogram V2 Edit API](https://fal.ai/docs/model-api-reference/image-generation-api/ideogram-v2-edit.md): API reference for Ideogram V2 Edit. Transform existing images with Ideogram V2's editing capabilities. Modify, adjust, and refine images while maintaining high fidelity and realistic outputs with prec
- [Ideogram V2 Remix API](https://fal.ai/docs/model-api-reference/image-generation-api/ideogram-v2-remix.md): API reference for Ideogram V2 Remix. Reimagine existing images with Ideogram V2's remix feature. Create variations and adaptations while preserving core elements and adding new creative directions thr
- [Ideogram V2 Turbo API](https://fal.ai/docs/model-api-reference/image-generation-api/ideogram-v2-turbo.md): API reference for Ideogram V2 Turbo. Accelerated image generation with Ideogram V2 Turbo. Create high-quality visuals, posters, and logos with enhanced speed while maintaining Ideogram's signature qua

##### V2a

- [Ideogram V2a API](https://fal.ai/docs/model-api-reference/image-generation-api/ideogram-v2a.md): API reference for Ideogram V2a. Generate high-quality images, posters, and logos with Ideogram V2A. Features exceptional typography handling and realistic outputs optimized for commercial and creative
- [Ideogram V2a Remix API](https://fal.ai/docs/model-api-reference/image-generation-api/ideogram-v2a-remix.md): API reference for Ideogram V2a Remix. Create variations of existing images with Ideogram V2A Remix while maintaining creative control through prompt guidance.
- [Ideogram V2a Turbo API](https://fal.ai/docs/model-api-reference/image-generation-api/ideogram-v2a-turbo.md): API reference for Ideogram V2a Turbo. Accelerated image generation with Ideogram V2A Turbo. Create high-quality visuals, posters, and logos with enhanced speed while maintaining Ideogram's signature q

#### Seedvr

##### Upscale

- [Seedvr Upscale Image API](https://fal.ai/docs/model-api-reference/image-generation-api/seedvr-upscale-image.md): API reference for Seedvr Upscale Image. Use SeedVR2 to upscale your images

#### Topaz

- [Topaz Upscale API](https://fal.ai/docs/model-api-reference/image-generation-api/topaz-upscale.md): API reference for Topaz Upscale. Use the powerful and accurate topaz image enhancer to enhance your images.

#### Xai

- [Xai Grok Imagine Image API](https://fal.ai/docs/model-api-reference/image-generation-api/xai-grok-imagine-image.md): API reference for Xai Grok Imagine Image. Generate highly aesthetic images with xAI's Grok Imagine Image generation model.

#### Z Image

- [Z Image Base API](https://fal.ai/docs/model-api-reference/image-generation-api/z-image-base.md): API reference for Z Image Base. Z-Image is the foundation model of the Z- Image family, engineered for good quality, robust generative diversity, broad stylistic coverage, and precise prompt adherence

##### Turbo

- [Z Image Turbo API](https://fal.ai/docs/model-api-reference/image-generation-api/z-image-turbo.md): API reference for Z Image Turbo. Z-Image Turbo is a super fast text-to-image model of 6B parameters developed by Tongyi-MAI.
- [Z Image Turbo Controlnet API](https://fal.ai/docs/model-api-reference/image-generation-api/z-image-turbo-controlnet.md): API reference for Z Image Turbo Controlnet. Generate images from text and edge, depth or pose images using Z-Image Turbo, Tongyi-MAI's super-fast 6B model.
- [Z Image Turbo Image To Image API](https://fal.ai/docs/model-api-reference/image-generation-api/z-image-turbo-image-to-image.md): API reference for Z Image Turbo Image To Image. Generate images from text and images using Z-Image Turbo, Tongyi-MAI's super-fast 6B model.
- [Z Image Turbo Inpaint API](https://fal.ai/docs/model-api-reference/image-generation-api/z-image-turbo-inpaint.md): API reference for Z Image Turbo Inpaint. Generate images from text, an image and a mask using Z-Image Turbo, Tongyi-MAI's super-fast 6B model.
- [Z Image Turbo Lora API](https://fal.ai/docs/model-api-reference/image-generation-api/z-image-turbo-lora.md): API reference for Z Image Turbo Lora. Text-to-Image endpoint with LoRA support for Z-Image Turbo, a super fast text-to-image model of 6B parameters developed by Tongyi-MAI.
- [Z Image Turbo Tiling API](https://fal.ai/docs/model-api-reference/image-generation-api/z-image-turbo-tiling.md): API reference for Z Image Turbo Tiling. Generate seamlessly tiling photorealistic images from text using Z-Image Turbo

### Audio

- [Audio API](https://fal.ai/docs/model-api-reference/audio-api/overview.md): Audio API reference. Models for audio processing including text-to-speech, speech-to-text, voice cloning, and music generation..
- [Whisper API](https://fal.ai/docs/model-api-reference/audio-api/whisper.md): API reference for Whisper. Whisper is a model for speech transcription and translation.

#### Kling Video

- [Kling Video Create Voice API](https://fal.ai/docs/model-api-reference/audio-api/kling-video-create-voice.md): API reference for Kling Video Create Voice. Create Voices to be used with Kling Models Voice Control
- [Kling Video V1 API](https://fal.ai/docs/model-api-reference/audio-api/kling-video-v1.md): API reference for Kling Video V1. Generate speech from text prompts and different voices using the Kling TTS model, which leverages advanced AI techniques to create high-quality text-to-speech.
- [Kling Video Video To Audio API](https://fal.ai/docs/model-api-reference/audio-api/kling-video-video-to-audio.md): API reference for Kling Video Video To Audio. Generate audio from input videos using Kling

#### Xai

- [Xai Tts API](https://fal.ai/docs/model-api-reference/audio-api/xai-tts.md): API reference for Xai Tts. Generate speech with expressive and realistic voices from xAI

### Vision

- [Vision API](https://fal.ai/docs/model-api-reference/vision-api/overview.md): Vision API reference. Models for understanding and analyzing images, including captioning, visual question answering, and object detection..
- [Florence 2 Large API](https://fal.ai/docs/model-api-reference/vision-api/florence-2-large.md): API reference for Florence 2 Large. Florence-2 is an advanced vision foundation model that uses a prompt-based approach to handle a wide range of vision and vision-language tasks
- [Imageutils API](https://fal.ai/docs/model-api-reference/vision-api/imageutils.md): API reference for Imageutils. Predict the probability of an image being NSFW.

#### Openrouter

- [Openrouter Router API](https://fal.ai/docs/model-api-reference/vision-api/openrouter-router.md): API reference for Openrouter Router. Run any Vision Language Model with fal. Analyze and understand images using Claude (Anthropic), GPT-5 / GPT-4o (OpenAI), Gemini (Google), Grok (xAI), Llama (Meta),

### 3D

- [3D API](https://fal.ai/docs/model-api-reference/3d-api/overview.md): 3D API reference. Generate 3D assets from text or images using AI models.
- [Trellis API](https://fal.ai/docs/model-api-reference/3d-api/trellis.md): API reference for Trellis. Generate 3D models from your images using Trellis. A native 3D generative model enabling versatile and high-quality 3D asset creation.
- [Trellis 2 API](https://fal.ai/docs/model-api-reference/3d-api/trellis-2.md): API reference for Trellis 2. Generate 3D models from your images using Trellis 2. A native 3D generative model enabling versatile and high-quality 3D asset creation.

#### Hunyuan 3d

##### V3.1

- [Hunyuan 3d V3.1 Part API](https://fal.ai/docs/model-api-reference/3d-api/hunyuan-3d-v3.1-part.md): API reference for Hunyuan 3d V3.1 Part. Split 3D models into parts with Hunyuan 3D
- [Hunyuan 3d V3.1 Pro API](https://fal.ai/docs/model-api-reference/3d-api/hunyuan-3d-v3.1-pro.md): API reference for Hunyuan 3d V3.1 Pro. Generate 3D models from images with Hunyuan 3D Pro
- [Hunyuan 3d V3.1 Rapid API](https://fal.ai/docs/model-api-reference/3d-api/hunyuan-3d-v3.1-rapid.md): API reference for Hunyuan 3d V3.1 Rapid. Rapidly generate 3D models from images using Hunyuan 3D.
- [Hunyuan 3d V3.1 Smart Topology API](https://fal.ai/docs/model-api-reference/3d-api/hunyuan-3d-v3.1-smart-topology.md): API reference for Hunyuan 3d V3.1 Smart Topology. Optimize 3D mesh topology with Hunyuan 3D Smart Topology.
