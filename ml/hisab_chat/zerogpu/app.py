"""Hisab-Chat on a Hugging Face ZeroGPU Space.

Capzoryx calls the `chat` API with the same messages it sends any provider (system prompt with the business facts,
recent turns, the question) and gets the reply text back. A GPU is attached only while a reply is generated.
"""
import json
import os

import gradio as gr
import spaces
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

REPO = os.environ.get('MODEL_REPO', 'Pranto-404/hisab-chat-merged')
TOKEN = os.environ.get('HF_TOKEN')
tokenizer = AutoTokenizer.from_pretrained(REPO, token=TOKEN)
model = AutoModelForCausalLM.from_pretrained(REPO, token=TOKEN, torch_dtype=torch.bfloat16)
model.to('cuda')  # ZeroGPU moves this to a real GPU inside each @spaces.GPU call


@spaces.GPU(duration=40)
def chat(messages_json: str, max_tokens: float = 500) -> str:
    messages = [m for m in json.loads(messages_json) if m.get('role') in ('system', 'user', 'assistant')][-14:]
    ids = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors='pt').to('cuda')
    out = model.generate(ids, max_new_tokens=max(32, min(int(max_tokens), 800)), do_sample=True, temperature=0.6, top_p=0.9,
                         repetition_penalty=1.05, pad_token_id=tokenizer.eos_token_id)
    return tokenizer.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()


demo = gr.Interface(fn=chat, inputs=[gr.Textbox(label='messages (JSON list of {role, content})', lines=6),
                                     gr.Number(value=500, label='max new tokens')],
                    outputs=gr.Textbox(label='reply'), title='Hisab-Chat', api_name='chat',
                    description='Capzoryx business assistant model. Called by the Capzoryx server.')
demo.queue(max_size=16).launch()
