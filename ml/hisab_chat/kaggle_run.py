"""One-cell Kaggle run: build data, train Hisab-Chat, publish it and start its free Hugging Face Space.

In a Kaggle notebook (Accelerator: GPU T4 x2, Internet: on) add these secrets under Add-ons -> Secrets:
HF_TOKEN (Hugging Face write token) and any of GROQ_KEY, GEMINI_KEY, CEREBRAS_KEY, OPENROUTER_KEY. Then run:

    !git clone -q https://github.com/Pranto-404/Capzoryx
    %run Capzoryx/ml/hisab_chat/kaggle_run.py

Use Save Version -> Save & Run All to keep it running with the browser closed. It ends by printing the two values
to add on Render.
"""
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWNER = os.getenv('HISAB_OWNER', 'Pranto-404')
MODEL_REPO, SPACE_REPO = f'{OWNER}/hisab-chat-gguf', f'{OWNER}/hisab-chat'
TEACHER_SECRETS = {'GROQ_KEY': 'CAPZORYX_CHAT_GROQ_KEY', 'GEMINI_KEY': 'CAPZORYX_CHAT_GEMINI_KEY',
                   'CEREBRAS_KEY': 'CAPZORYX_CHAT_CEREBRAS_KEY', 'OPENROUTER_KEY': 'CAPZORYX_CHAT_OPENROUTER_KEY'}


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


def main():
    load_secrets()
    if not os.getenv('HF_TOKEN'):
        raise SystemExit('Add a Hugging Face write token as the Kaggle secret HF_TOKEN.')
    teachers = [env for env in TEACHER_SECRETS.values() if os.getenv(env)]
    print('Teachers available:', ', '.join(teachers) or 'none (template data only)')
    step('Install training libraries', sys.executable, '-m', 'pip', '-q', 'install', 'unsloth', 'httpx')
    step('Build conversations', sys.executable, '-m', 'ml.hisab_chat.build_dataset', '--out', 'data/hisab_chat',
         '--size', '6000', '--teacher', '1500' if teachers else '0')
    step('Train, export and upload', sys.executable, '-m', 'ml.hisab_chat.train', '--data', 'data/hisab_chat',
         '--output', 'runs/hisab-chat', '--epochs', '1', '--gguf', '--push', MODEL_REPO)
    key = start_space()
    print('\n=== Done ===')
    print('Model:', f'https://huggingface.co/{MODEL_REPO}')
    print('Space (takes ~5 minutes to start):', f'https://huggingface.co/spaces/{SPACE_REPO}')
    print('\nAdd these two Environment variables on Render (capzoryx-staging-api):')
    print(f"  CAPZORYX_CHAT_HISAB_URL = https://{SPACE_REPO.replace('/', '-').lower()}.hf.space/v1")
    print(f'  CAPZORYX_CHAT_HISAB_KEY = {key}')


if __name__ == '__main__':
    main()
