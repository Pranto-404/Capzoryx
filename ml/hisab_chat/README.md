# Hisab-Chat: train and serve Capzoryx's own chat model on one RTX 5060 Ti

Hisab-Chat is the first model the Telegram and in-app chat try (`api/app/chat/llm.py`). Free API tiers
are only the fallback. Everything below is free: open models, your own GPU and a free Cloudflare tunnel.

## No PC needed: one Kaggle cell trains, publishes and starts the model

Nothing is installed on your computer, and it keeps running with the browser closed.

1. **Hugging Face token**: huggingface.co → Settings → Access Tokens → New token, type **Write**.
2. **Kaggle**: kaggle.com → Create → New Notebook (keep it private). Settings → Accelerator **GPU T4 x2**,
   Internet **on**. Add-ons → Secrets: `HF_TOKEN`, plus any of `GROQ_KEY`, `GEMINI_KEY`, `CEREBRAS_KEY`,
   `OPENROUTER_KEY` (free keys; they write the natural conversations within their daily budgets).
3. Paste one cell and press **Save Version → Save & Run All**:

   ```python
   !git clone -q https://github.com/Pranto-404/Capzoryx
   %run Capzoryx/ml/hisab_chat/kaggle_run.py
   ```

   About 1–1.5 hours later the log ends with two values. It has built the data, trained Hisab-Chat (one epoch),
   uploaded it privately to `Pranto-404/hisab-chat-gguf`, and created the `Pranto-404/hisab-chat` Space that serves it.
4. **Render** → `capzoryx-staging-api` → Environment: add `CAPZORYX_CHAT_HISAB_URL` and `CAPZORYX_CHAT_HISAB_KEY`
   with those two values. The bot then asks Hisab-Chat first.

A free Space sleeps after two days without requests and takes a minute to wake; during that minute the free API
fallbacks answer.

## With your own GPU (RTX 5060 Ti)

### 1. Set up (Windows: use WSL2 Ubuntu)

```bash
python3.12 -m venv ~/hisab && source ~/hisab/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu128   # RTX 50-series needs CUDA 12.8+
pip install -r ml/hisab_lm/requirements-gpu.lock.txt                   # unsloth, transformers, peft, datasets
pip install -r api/requirements.lock.txt
nvidia-smi                                                             # the 5060 Ti should be listed
git clone https://github.com/ggml-org/llama.cpp && cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=ON \
  && cmake --build llama.cpp/build -j --target llama-server && export PATH=$PWD/llama.cpp/build/bin:$PATH
```

### 2. Full-speed pipeline on a 16 GB card

The GPU does the bulk work; free API teachers are only used for grading, within a daily budget that leaves 30% of
each quota for the live bot (`teachers.py`, usage kept in `~/.cache/capzoryx/teacher_usage.json`).

**A. Teacher on the GPU writes natural conversations (~30–40 min).** Qwen3-30B-A3B is a mixture-of-experts model:
30B parameters of knowledge, but only 3B work on each word, so it runs about as fast as a small model. In 4-bit it
needs ~19 GB, so `--n-cpu-moe` keeps some expert layers in system RAM (32 GB is enough) and the rest on the GPU.
With 16 GB of RAM use `ggml-org/gemma-3-12b-it-GGUF:Q4_K_M` without `--n-cpu-moe` instead.

```bash
TEACHER=unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF:Q4_K_M
llama-server -hf $TEACHER --port 8081 -ngl 99 --n-cpu-moe 16 -c 16384 -np 8 -fa on &
python -m ml.hisab_chat.build_dataset --out data/hisab_chat --size 6000 --teacher 3000 \
    --local-teacher-url http://127.0.0.1:8081/v1 --workers 8
```

**B. Train (~30–45 min).** Stop the teacher first (`kill %1`) so training has the whole card. On 16 GB the 4B model
trains in 16-bit (faster and more accurate than 4-bit); add `--qlora` only if it runs out of memory.

```bash
python -m ml.hisab_chat.train --data data/hisab_chat --output runs/hisab-chat --gguf
```

**C. Self-play round (~20–30 min).** Student and teacher share the card:

```bash
llama-server -m runs/hisab-chat/gguf/hisab-chat-q4_k_m.gguf --port 8080 -ngl 99 -c 8192 -np 8 --api-key LOCAL &
llama-server -hf $TEACHER --port 8081 -ngl 99 --n-cpu-moe 26 -c 16384 -np 8 -fa on &   # more experts in RAM: the student uses part of the GPU
python -m ml.hisab_chat.self_play --student-url http://127.0.0.1:8080/v1 --student-key LOCAL \
    --local-teacher-url http://127.0.0.1:8081/v1 --examples 600 --workers 8 --minutes 40 \
    --out data/hisab_chat/selfplay-r1.jsonl
```

The GPU teacher writes the test questions in twelve styles (typos, slang, formal, follow-ups, unsafe and off-topic).
Grading and rewrites go to the strongest teacher with budget left: Groq, Cerebras, Mistral, OpenRouter, Gemini or
GitHub Models when their `CAPZORYX_CHAT_*_KEY` is set, otherwise the GPU teacher. Rewrites that state an amount not in
the facts, or answer in the wrong language, are dropped. `selfplay-r1.report.json` records the mean score and the API
calls spent today.

**D. Merge and retrain (~40 min), then publish.**

```bash
kill %1 %2
python -m ml.hisab_chat.build_dataset --out data/hisab_chat --size 6000 --teacher 3000 \
    --local-teacher-url http://127.0.0.1:8081/v1 --extra data/hisab_chat/selfplay-r1.jsonl   # restart the step-A teacher first
python -m ml.hisab_chat.train --data data/hisab_chat --output runs/hisab-chat-r2 --gguf --push Pranto-404/hisab-chat-gguf
```

Repeat C–D (`-r2`, `-r3`) while the mean score keeps rising. One full round takes about 2–2.5 hours.

If llama-server reports it is out of memory, raise `--n-cpu-moe` by 4 and start it again; if the GPU sits below
~90% in `nvidia-smi` and memory is free, lower it by 4 for more speed.

### 3. Measure before you claim

```bash
llama-server -m runs/hisab-chat/gguf/*.gguf --port 8080 -ngl 99 -c 4096 --api-key YOUR_LOCAL_KEY &
python -m ml.hisab_chat.eval --data data/hisab_chat --url http://127.0.0.1:8080/v1 --model hisab-chat --key YOUR_LOCAL_KEY
python -m ml.hisab_chat.eval --data data/hisab_chat --url https://api.groq.com/openai/v1 --model llama-3.3-70b-versatile --key $CAPZORYX_CHAT_GROQ_KEY
```

Report `grounded` (no invented amounts), `fact_recall`, `language_match` and latency side by side. Before you
present them, add a hand-written test set from real speakers; the bundled validation split is synthetic.

### 4. Serve it to the live bot

```bash
llama-server -m runs/hisab-chat/gguf/*.gguf --host 127.0.0.1 --port 8080 -ngl 99 -c 4096 --api-key YOUR_LOCAL_KEY
cloudflared tunnel --url http://127.0.0.1:8080          # free; prints https://<name>.trycloudflare.com
```

On the Render API service set `CAPZORYX_CHAT_HISAB_URL=https://<name>.trycloudflare.com/v1` and
`CAPZORYX_CHAT_HISAB_KEY=YOUR_LOCAL_KEY`. When your PC is off, the bot uses the free API fallbacks automatically.
A quick-tunnel address changes on every restart; a free Cloudflare account with a named tunnel keeps it fixed.
