# Hisab-Chat: train and serve Capzoryx's own chat model on one RTX 5060 Ti

Hisab-Chat is the first model the Telegram and in-app chat try (`api/app/chat/llm.py`). Free API tiers
are only the fallback. Everything below is free: open models, your own GPU and a free Cloudflare tunnel.

## No PC needed: train on Kaggle's free GPU, serve on a free Hugging Face Space

Everything below runs in a browser, so it works from a phone and your PC can stay off.

1. **Hugging Face token**: huggingface.co → Settings → Access Tokens → New token, type **Write**.
2. **Kaggle**: kaggle.com → Create → New Notebook. Settings → Accelerator **GPU T4 x2**, Internet **on**.
   Add-ons → Secrets → add `HF_TOKEN` (the token) and `GROQ_KEY` (a free key from console.groq.com). Then run these three cells:

   ```python
   !git clone -q https://github.com/Pranto-404/Capzoryx && pip -q install unsloth httpx
   ```
   ```python
   import os; from kaggle_secrets import UserSecretsClient
   secrets = UserSecretsClient(); os.chdir('/kaggle/working/Capzoryx')
   os.environ['HF_TOKEN'] = secrets.get_secret('HF_TOKEN'); os.environ['CAPZORYX_CHAT_GROQ_KEY'] = secrets.get_secret('GROQ_KEY')
   !python -m ml.hisab_chat.build_dataset --out data/hisab_chat --size 6000 --teacher 3000
   ```
   ```python
   !python -m ml.hisab_chat.train --data data/hisab_chat --output runs/hisab-chat --gguf --push Pranto-404/hisab-chat-gguf
   ```
   Training takes about 2–3 hours on a T4. The notebook can keep running with the browser tab closed if you use
   **Save Version → Save & Run All**. The model lands privately in `Pranto-404/hisab-chat-gguf`.
3. **Space**: huggingface.co → New Space → name `hisab-chat`, SDK **Docker**, hardware **CPU basic (free)**, private.
   Upload `ml/hisab_chat/space/Dockerfile` and `README.md`. In the Space settings add secrets `HF_TOKEN` (the same
   token) and `LLAMA_API_KEY` (any long random text).
4. **Render**: on `capzoryx-staging-api` set `CAPZORYX_CHAT_HISAB_URL=https://pranto-404-hisab-chat.hf.space/v1` and
   `CAPZORYX_CHAT_HISAB_KEY` to the same `LLAMA_API_KEY`.

The bot then asks Hisab-Chat first. A free Space sleeps after two days without requests and takes a minute to wake;
during that minute the free API fallbacks answer.

## With your own GPU (RTX 5060 Ti)

### 1. Set up (Windows: use WSL2 Ubuntu)

```bash
python3.12 -m venv ~/hisab && source ~/hisab/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu128   # RTX 50-series needs CUDA 12.8+
pip install -r ml/hisab_lm/requirements-gpu.lock.txt                   # unsloth, transformers, peft, datasets
pip install -r api/requirements.lock.txt
nvidia-smi                                                             # the 5060 Ti should be listed
```

### 2. Build the data

```bash
export CAPZORYX_CHAT_GROQ_KEY=...   # free key from console.groq.com (more free keys = more teacher variety)
python -m ml.hisab_chat.build_dataset --out data/hisab_chat --size 6000 --teacher 3000
```

Why the teacher matters: in the live bot, figures, greetings and misspelt questions are answered by the
deterministic brain (`api/app/chat/understand.py`, tested on noisy and formal messages). Hisab-Chat only receives
open questions — advice, explanations, small talk — so its quality comes mostly from the teacher conversations.
Every teacher reply must pass the same number check the live bot uses.

Questions are rewritten the way owners type (typos, short Banglish such as "kto"/"kmn", capitals, no punctuation,
"vai"/"apu", and formal phrasing with formal answers; see `augment.py`). No real customer data is used.

### 3. Train at full speed

```bash
python -m ml.hisab_chat.train --data data/hisab_chat --output runs/hisab-chat --gguf
```

| Base | VRAM | Time for 8k chats, 2 epochs (approx.) |
| --- | --- | --- |
| `Qwen/Qwen3-4B-Instruct-2507` (default) | 8 GB or 16 GB | 40–70 min |
| `google/gemma-3-12b-it` (`--base`) | 16 GB | 2–3 h |

The script uses 4-bit QLoRA, bf16, 8-bit AdamW and gradient checkpointing, which keeps the GPU fully busy without
running out of memory. `runs/hisab-chat/training.json` records the base, data hashes, loss and GPU.

### 3b. Self-play rounds: a big model quizzes, grades and corrects Hisab-Chat

After the first training run, serve the model (step 5's `llama-server` line) and let the teacher test it:

```bash
python -m ml.hisab_chat.self_play --student-url http://127.0.0.1:8080/v1 --student-key YOUR_LOCAL_KEY \
    --examples 600 --out data/hisab_chat/selfplay-r1.jsonl
python -m ml.hisab_chat.build_dataset --out data/hisab_chat --size 6000 --teacher 2000 --extra data/hisab_chat/selfplay-r1.jsonl
python -m ml.hisab_chat.train --data data/hisab_chat --output runs/hisab-chat-r2 --gguf --push Pranto-404/hisab-chat-gguf
```

The teacher writes realistic owner messages in twelve styles (typos, slang, formal, follow-ups, unsafe and off-topic
requests), grades each answer from 1 to 5 and rewrites the weak ones. Rewrites that state an amount not in the facts,
or answer in the wrong language, are dropped. `selfplay-r1.report.json` records the mean score; repeat with
`-r2`, `-r3` and keep going while the mean score rises. About 1.2 teacher calls per example fit the free Groq limits.

### 4. Measure before you claim

```bash
llama-server -m runs/hisab-chat/gguf/*.gguf --port 8080 -ngl 99 -c 4096 --api-key YOUR_LOCAL_KEY &
python -m ml.hisab_chat.eval --data data/hisab_chat --url http://127.0.0.1:8080/v1 --model hisab-chat --key YOUR_LOCAL_KEY
python -m ml.hisab_chat.eval --data data/hisab_chat --url https://api.groq.com/openai/v1 --model llama-3.3-70b-versatile --key $CAPZORYX_CHAT_GROQ_KEY
```

Report `grounded` (no invented amounts), `fact_recall`, `language_match` and latency side by side. Before you
present them, add a hand-written test set from real speakers; the bundled validation split is synthetic.

### 5. Serve it to the live bot

```bash
llama-server -m runs/hisab-chat/gguf/*.gguf --host 127.0.0.1 --port 8080 -ngl 99 -c 4096 --api-key YOUR_LOCAL_KEY
cloudflared tunnel --url http://127.0.0.1:8080          # free; prints https://<name>.trycloudflare.com
```

On the Render API service set `CAPZORYX_CHAT_HISAB_URL=https://<name>.trycloudflare.com/v1` and
`CAPZORYX_CHAT_HISAB_KEY=YOUR_LOCAL_KEY`. When your PC is off, the bot uses the free API fallbacks automatically.
A quick-tunnel address changes on every restart; a free Cloudflare account with a named tunnel keeps it fixed.
