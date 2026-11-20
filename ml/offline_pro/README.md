# Offline Pro browser preview

This local prototype exercises the plan's browser architecture on a computer with WebGPU and shader-f16. WebLLM 0.2.89 lists 1,403.34 MB of GPU memory for Qwen3 0.6B q4f16_1. The model may generate incorrect English or Bangla, amounts and dates. It has no access to workspace records and cannot send or record a payment. No model ships in the website or APK.

## Prepare a local pack

1. On Wi-Fi, obtain a reviewed immutable snapshot of [MLC's Qwen3 0.6B q4f16_1 conversion](https://huggingface.co/mlc-ai/Qwen3-0.6B-q4f16_1-MLC). Keep the source revision, model card, model and tokenizer licenses and notices. Verify redistribution terms before hosting any files publicly. Select the small 0.6B variant.
2. From the reviewed revision of [MLC's model libraries](https://github.com/mlc-ai/binary-mlc-llm-libs), place `web-llm-models/v0_2_87/base/Qwen3-0.6B-q4f16_1_cs1k-webgpu.wasm` in the same local pack directory. Preserve the runtime license. Use the upstream SHA-256/LFS object IDs or hashes of reviewer-authenticated artifacts to prepare a JSON object mapping each file's basename to its SHA-256 digest. Include the chat config, tokenizer files, ndarray cache index, every shard and the WASM library. Keep that manifest outside the pack. The server verifies each startup asset before opening its port.
3. From this folder run `npm ci --ignore-scripts` while online. Disconnect from the internet, then run `python3.11 serve.py /path/to/local-pack /path/to/reviewed-checksums.json`. Python 3.11 or newer is required. At `http://127.0.0.1:8764` select **Load local model**. Model loading begins only on that click. The server reads files from disk, only answers loopback requests and has no download endpoint. The browser uses WebGPU with a WebAssembly permission scoped to this standalone origin. Selecting **Unload model** releases inference resources. Clear the loopback site's browser storage to remove any cached assets.

## Release evidence

The plan calls for a reviewed self-hosted pack and LiteRT-LM on Android. Public hosting, model redistribution notices, real-device peak memory, an airplane-mode completion and Bengali quality scores need validation before shipping. The Android engine requires a separately converted and licensed LiteRT-LM model and a physical device benchmark. This WebLLM pack targets WebGPU and cannot be passed to LiteRT-LM. The main website and Android build do not download weights.
