"""QLoRA fine-tune of Hisab-Chat on one consumer GPU (tuned for an RTX 5060 Ti, 16 GB or 8 GB).

    python -m ml.hisab_chat.train --data data/hisab_chat --output runs/hisab-chat --gguf
    python -m ml.hisab_chat.train --data data/hisab_chat --output runs/hisab-chat-12b --base google/gemma-3-12b-it --gguf

Loss is computed on assistant turns only, so the model learns to answer rather than to repeat the facts block.
"""
import argparse
import hashlib
import json
from pathlib import Path

BASES = {
    'Qwen/Qwen3-4B-Instruct-2507': dict(batch=4, accumulate=4),  # fits 8 GB and 16 GB
    'google/gemma-3-12b-it': dict(batch=1, accumulate=16),       # heavier, needs 16 GB
    'Qwen/Qwen3-1.7B': dict(batch=8, accumulate=2),              # quick smoke run
}
MAX_LEN = 1536
SEED = 20261121


def load(data):
    manifest = json.loads((data / 'manifest.json').read_text())
    rows = {}
    for name in ('train', 'validation'):
        raw = (data / f'{name}.jsonl').read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest['splits'][name]['sha256']:
            raise SystemExit(f'{name}.jsonl does not match manifest.json; rebuild the dataset')
        rows[name] = [json.loads(line) for line in raw.splitlines()]
        if any(not r['source'].startswith('synthetic') for r in rows[name]):
            raise SystemExit('Only synthetic conversations belong in this corpus')
    return rows, manifest


def encode(tokenizer, messages):
    """Token ids for the whole chat, with labels only on assistant replies."""
    ids, labels = [], []
    for end in range(1, len(messages) + 1):
        if messages[end - 1]['role'] != 'assistant':
            continue
        prompt = tokenizer.apply_chat_template(messages[:end - 1], add_generation_prompt=True, tokenize=True)
        full = tokenizer.apply_chat_template(messages[:end], tokenize=True)
        if full[:len(prompt)] != prompt or full[:len(ids)] != ids:
            raise ValueError('Chat template is not prefix-stable; choose an instruct base model')
        labels += [-100] * (len(prompt) - len(ids)) + full[len(prompt):]
        ids = full
    if len(ids) > MAX_LEN:
        return None
    return dict(input_ids=ids, labels=labels)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--base', choices=sorted(BASES), default='Qwen/Qwen3-4B-Instruct-2507')
    p.add_argument('--epochs', type=int, default=2)
    p.add_argument('--gguf', action='store_true', help='also export a q4_k_m GGUF for llama.cpp or Ollama')
    a = p.parse_args()
    rows, manifest = load(a.data)

    import torch
    if not torch.cuda.is_available():
        raise SystemExit('A CUDA GPU is required. RTX 50-series cards need a PyTorch build for CUDA 12.8 or newer.')
    from datasets import Dataset
    from transformers import Trainer, TrainingArguments
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(model_name=a.base, max_seq_length=MAX_LEN, load_in_4bit=True)
    model = FastLanguageModel.get_peft_model(model, r=32, lora_alpha=32, lora_dropout=0.0, bias='none',
                                             target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'],
                                             use_gradient_checkpointing='unsloth', random_state=SEED)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    sets = {name: Dataset.from_list([e for e in (encode(tokenizer, r['messages']) for r in group) if e])
            for name, group in rows.items()}

    def collate(batch):
        width = max(len(r['input_ids']) for r in batch)
        pad = lambda field, value: torch.tensor([r[field] + [value] * (width - len(r[field])) for r in batch])
        mask = torch.tensor([[1] * len(r['input_ids']) + [0] * (width - len(r['input_ids'])) for r in batch])
        return {'input_ids': pad('input_ids', tokenizer.pad_token_id), 'labels': pad('labels', -100), 'attention_mask': mask}

    plan = BASES[a.base]
    args = TrainingArguments(
        output_dir=str(a.output / 'checkpoints'), num_train_epochs=a.epochs, seed=SEED, report_to='none',
        per_device_train_batch_size=plan['batch'], gradient_accumulation_steps=plan['accumulate'],
        per_device_eval_batch_size=plan['batch'], learning_rate=2e-4, lr_scheduler_type='cosine', warmup_ratio=0.03,
        weight_decay=0.01, bf16=torch.cuda.is_bf16_supported(), fp16=not torch.cuda.is_bf16_supported(),
        optim='adamw_8bit', logging_steps=10, eval_strategy='epoch', save_strategy='epoch', save_total_limit=2,
        load_best_model_at_end=True, metric_for_best_model='eval_loss', greater_is_better=False,
        dataloader_num_workers=2, group_by_length=True)
    trainer = Trainer(model=model, args=args, train_dataset=sets['train'], eval_dataset=sets['validation'],
                      data_collator=collate)
    trainer.train()
    adapter = a.output / 'adapter'
    model.save_pretrained(str(adapter))
    tokenizer.save_pretrained(str(adapter))
    if a.gguf:
        model.save_pretrained_gguf(str(a.output / 'gguf'), tokenizer, quantization_method='q4_k_m')
    evidence = dict(base=a.base, dataset=manifest['splits'], epochs=a.epochs, seed=SEED,
                    best_validation_loss=trainer.state.best_metric, gpu=torch.cuda.get_device_name(0))
    (a.output / 'training.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence))


if __name__ == '__main__':
    main()
