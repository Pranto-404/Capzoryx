"""One-cell Kaggle run: build data, train Hisab-Chat, publish it and start its free Hugging Face Space.

In a Kaggle notebook (Accelerator: GPU T4 x2, Internet: on) add these secrets under Add-ons -> Secrets:
HF_TOKEN (Hugging Face write token) and any of GROQ_KEY, GEMINI_KEY, CEREBRAS_KEY, OPENROUTER_KEY. Then run:

    !rm -rf Capzoryx && git clone -q https://github.com/Pranto-404/Capzoryx
    %run Capzoryx/ml/hisab_chat/kaggle_run.py

Use Save Version -> Save & Run All to keep it running with the browser closed. It ends by printing the values
to add on Render.

ZeroGPU (needs a Hugging Face PRO account): put `%env HISAB_TARGET=zerogpu` above the %run line. The run then also
uploads merged 16-bit weights and starts a private Gradio Space on ZeroGPU, which answers far faster than the free
CPU Space. Total time on a T4 is about 2 hours (data ~25 min with teachers, training ~60-75 min, upload ~15 min).
"""
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWNER = os.getenv('HISAB_OWNER', 'Pranto-404')
MODEL_REPO, SPACE_REPO = f'{OWNER}/hisab-chat-gguf', f'{OWNER}/hisab-chat'
MERGED_REPO, ZERO_SPACE = f'{OWNER}/hisab-chat-merged', f'{OWNER}/hisab-chat-zero'
ZEROGPU = os.getenv('HISAB_TARGET', '').lower() == 'zerogpu'
# Free plan default: Qwen3-1.7B answers in 1-3 GPU seconds (many replies per free ZeroGPU quota) and still runs on a
# free 2-core CPU Space. HISAB_BASE=Qwen/Qwen3-4B-Instruct-2507 gives better Bangla at about twice the cost.
BASE = os.getenv('HISAB_BASE', 'Qwen/Qwen3-4B-Instruct-2507')
SMALL = '1.7B' in BASE
# Data size: 1.0 is about 6,900 conversations. The 4B default uses 60% so the whole run fits in about 2 hours on a T4.
SCALE = float(os.getenv('HISAB_SCALE', '1.0' if SMALL else '0.6'))
# A free 2-core CPU Space is only fast enough for the small model; the 4B one is served on ZeroGPU alone.
CPU_COPY = SMALL or not ZEROGPU or os.getenv('HISAB_CPU') == '1'
TEACHER_SECRETS = {'GROQ_KEY': 'CAPZORYX_CHAT_GROQ_KEY', 'GEMINI_KEY': 'CAPZORYX_CHAT_GEMINI_KEY',
                   'CEREBRAS_KEY': 'CAPZORYX_CHAT_CEREBRAS_KEY', 'OPENROUTER_KEY': 'CAPZORYX_CHAT_OPENROUTER_KEY',
                   'GITHUB_KEY': 'CAPZORYX_CHAT_GITHUB_KEY'}  # GitHub Models: a GitHub token with models:read (Student Pro works)


def step(title, *command):
    print(f'\n=== {title} ===', flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def load_secrets():
    try:
        from kaggle_secrets import UserSecretsClient
    except ImportError:  # outside Kaggle the values come from the environment
        return
    client = UserSecretsClient()
    for name, env in {'HF_TOKEN': 'HF_TOKEN', **TEACHER_SECRETS}.items():
        try:
            os.environ[env] = client.get_secret(name)
        except Exception:  # noqa: BLE001 - a missing optional secret is fine
            pass


def probe_teachers():
    """Pick each teacher's current model and send it one tiny request, so problems show at the start."""
    import httpx
    sys.path.insert(0, str(ROOT))
    from api.app.chat import llm
    working = []
    for provider in [p for p in llm.available() if not p.own]:
        provider.discover()
        try:
            reply = httpx.post(provider.url + '/chat/completions', timeout=30,
                               headers={'Authorization': 'Bearer ' + provider.key},
                               json={'model': provider.model_name, 'max_tokens': 5, 'messages': [{'role': 'user', 'content': 'hi'}]})
            status = reply.status_code
            detail = '' if status == 200 else ' ' + reply.text[:160].replace('\n', ' ')
        except httpx.HTTPError as error:
            status, detail = 'error', ' ' + type(error).__name__
        print(f'Teacher {provider.name}: model {provider.model_name} -> {status}{detail}', flush=True)
        if status == 200:
            working.append(provider.name)
            os.environ[f'CAPZORYX_CHAT_{provider.name.upper()}_MODEL'] = provider.model_name  # reuse in child steps
    print('Working teachers:', ', '.join(working) or 'none (template data only)', flush=True)
    return working


def start_space():
    from huggingface_hub import HfApi
    api = HfApi()
    api.create_repo(SPACE_REPO, repo_type='space', space_sdk='docker', exist_ok=True)
    for name in ('Dockerfile', 'README.md'):
        api.upload_file(path_or_fileobj=str(ROOT / 'ml/hisab_chat/space' / name), path_in_repo=name, repo_id=SPACE_REPO,
                        repo_type='space', commit_message='Serve Hisab-Chat')
    key = secrets.token_urlsafe(32)
    api.add_space_secret(SPACE_REPO, 'HF_TOKEN', os.environ['HF_TOKEN'])
    api.add_space_secret(SPACE_REPO, 'LLAMA_API_KEY', key)
    return key


def start_zerogpu_space():
    """A private Gradio Space on ZeroGPU that serves the merged model. Hosting ZeroGPU needs a PRO account."""
    from huggingface_hub import HfApi
    api = HfApi()
    try:
        api.create_repo(ZERO_SPACE, repo_type='space', space_sdk='gradio', space_hardware='zero-a10g', private=True, exist_ok=True)
    except Exception as error:  # noqa: BLE001 - explain the usual cause instead of a stack trace
        print('Could not create the ZeroGPU Space (ZeroGPU hosting needs Hugging Face PRO):', error)
        return False
    for name in ('app.py', 'requirements.txt', 'README.md'):
        api.upload_file(path_or_fileobj=str(ROOT / 'ml/hisab_chat/zerogpu' / name), path_in_repo=name, repo_id=ZERO_SPACE,
                        repo_type='space', commit_message='Serve Hisab-Chat on ZeroGPU')
    api.add_space_secret(ZERO_SPACE, 'HF_TOKEN', os.environ['HF_TOKEN'])
    api.add_space_variable(ZERO_SPACE, 'MODEL_REPO', MERGED_REPO)
    api.add_space_variable(ZERO_SPACE, 'GPU_SECONDS', '12' if SMALL else '20')
    return True


def main():
    load_secrets()
    if not os.getenv('HF_TOKEN'):
        raise SystemExit('Add a Hugging Face write token as the Kaggle secret HF_TOKEN.')
    teachers = probe_teachers()
    step('Install training libraries', sys.executable, '-m', 'pip', '-q', 'install', 'unsloth', 'httpx')
    # Short everyday chat plus whole-business answers (any industry), so the model knows the owner's business.
    n = lambda count: str(int(count * SCALE))
    step('Build conversations', sys.executable, '-m', 'ml.hisab_chat.build_dataset', '--out', 'data/hisab_chat',
         '--size', n(3000), '--teacher', n(800) if teachers else '0',
         '--business', n(2200), '--business-teacher', n(900) if teachers else '0')
    step('Train, export and upload', sys.executable, '-m', 'ml.hisab_chat.train', '--data', 'data/hisab_chat',
         '--output', 'runs/hisab-chat', '--epochs', '1', '--base', BASE, *([] if SMALL else ['--qlora']),
         *(['--gguf', '--push', MODEL_REPO] if CPU_COPY else []), *(['--merged', MERGED_REPO] if ZEROGPU else []))
    key = start_space() if CPU_COPY else None  # the free CPU copy answers when GPU quota is used up (small model only)
    cpu = f"https://{SPACE_REPO.replace('/', '-').lower()}.hf.space/v1"
    if ZEROGPU and start_zerogpu_space():
        print('\n=== Done: ZeroGPU first, free CPU copy second, free APIs last ===')
        print('Spaces (take ~5 minutes to build):', f'https://huggingface.co/spaces/{ZERO_SPACE}', f'https://huggingface.co/spaces/{SPACE_REPO}')
        print('\nAdd these Environment variables on Render (capzoryx-staging-api):')
        print(f"  CAPZORYX_CHAT_HISAB_URL      = https://{ZERO_SPACE.replace('/', '-').lower()}.hf.space")
        print('  CAPZORYX_CHAT_HISAB_MODE     = zerogpu')
        print('  CAPZORYX_CHAT_HISAB_KEY      = a Hugging Face READ token (Settings -> Access Tokens); its account pays the GPU minutes')
        if key:
            print(f'  CAPZORYX_CHAT_HISAB_CPU_URL  = {cpu}')
            print(f'  CAPZORYX_CHAT_HISAB_CPU_KEY  = {key}')
        return
    if not key:
        raise SystemExit('The ZeroGPU Space could not be created and no CPU copy was built. Rerun with HISAB_BASE=Qwen/Qwen3-1.7B.')
    print('\n=== Done ===')
    print('Model:', f'https://huggingface.co/{MODEL_REPO}')
    print('Space (takes ~5 minutes to start):', f'https://huggingface.co/spaces/{SPACE_REPO}')
    print('\nAdd these two Environment variables on Render (capzoryx-staging-api):')
    print(f"  CAPZORYX_CHAT_HISAB_URL = https://{SPACE_REPO.replace('/', '-').lower()}.hf.space/v1")
    print(f'  CAPZORYX_CHAT_HISAB_KEY = {key}')


if __name__ == '__main__':
    main()
