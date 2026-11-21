# Hisab-LM model card

**Status.** The synthetic dataset, training recipe, Ollama configuration and scoring tools are available. This repository has no trained Hisab-LM checkpoint or qualified task. The machine that produced the dataset had no CUDA GPU, installed Ollama model or approved cloud reference. Candidate selection, tuning, GGUF inference, CPU latency, comparison against the best allowed provider and native-speaker ratings remain unmeasured.

## Training data

Use the downloadable MIT-licensed [synthetic training archive](../../web/public/datasets/hisab-lm-synthetic-v1.zip). It contains 3,600 distinct prompts in Bangla, Banglish and English, split into 2,880 training, 360 validation and 360 synthetic test examples. Six equally represented task families cover transaction extraction, printed bill text, quoted loan terms, cash briefings, reminder drafts and selection of read-only financial tools. Bills use generated transcriptions. Each output is checked before inclusion, including replaying tool choices on an in-memory financial dataset. The archive manifest contains per-split checksums. The SHA-256 of this release is `31239d4b85ddb7fdc1aba9c21f5e41cd68f16ef687c19aed0d15bda985e7d0a9`.

Rebuild using the project's pinned backend environment from the repository root.

```sh
python -m ml.hisab_lm.build_dataset --output .private/hisab-lm-synthetic-v1.zip
```

The public test split shares the generator's templates. Publish scores on it as synthetic. Reserve original team-authored material for a separately frozen evaluation. The generator and training job never ingest customer or production records.

## Candidate selection, training and deployment

Run each locally installed Qwen3-1.7B, Qwen3-4B and Gemma3-4B candidate on the same 100 validation examples with `--split validation --limit 100`. Reserve the test split for the chosen, frozen model. Record model and digest, download size, extraction and Bangla accuracy, CPU p95 and hardware. Choose the smallest model with acceptable measured accuracy and review the [licensing record](LICENSES/teachers.md). Use the owner’s CUDA PC or open [the training notebook](train.ipynb) on a free CUDA runtime. It resolves an exact model revision and runs 4-bit LoRA with rank 16, alpha 32, dropout 0.05, effective batch size 16, context 2,048, learning rate 0.0002 and a cosine schedule. It checks validation loss every half epoch across two epochs and exports the best checkpoint. Use the generated training.json and base revision when updating this card.

Place the resulting GGUF beside the Modelfile with the filename it specifies. Run `ollama create hisab-lm -f Modelfile` in that directory. Keep the GGUF and adapters outside Git and retain the chosen model's notices. Deploy to the optional loopback service on the demonstration computer only after review.

```sh
python -m ml.hisab_lm.eval --archive web/public/datasets/hisab-lm-synthetic-v1.zip \
  --ollama-model hisab-lm --predictions .private/hisab-lm-test.jsonl
python -m ml.hisab_lm.eval --archive web/public/datasets/hisab-lm-synthetic-v1.zip \
  --predictions .private/hisab-lm-test.jsonl --reference .private/approved-provider-test.jsonl
```

Prediction files contain one object per selected test ID with the model's raw `text` and optional `latency_ms`. Compare model output against verified structured facts. Review 30 Bangla responses with a native speaker and run the deterministic financial checks for each supported task. The release thresholds are extraction within five percentage points of the best allowed reference, at least 99% schema validity and zero invented numbers. The gateway permits only explicitly enabled local tasks. Keep its task list empty until the task-specific scorecard and privacy review are complete.
