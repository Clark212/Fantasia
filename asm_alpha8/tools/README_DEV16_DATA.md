# Making training data for ASM on your PC (DEV16)

Your computer runs an open-source model that writes realistic bugs into real open-source code. ASM then checks every
one in its sandbox and learns only from the ones that really break the project's tests. The model is never part of ASM.

## 1. Install Ollama and the model (once)
1. Install Ollama from https://ollama.com (Windows installer; it includes AMD GPU support for the RX 7600).
2. Open a terminal (PowerShell) and run:
   ```
   ollama pull qwen2.5-coder:7b
   ollama run qwen2.5-coder:7b "write a python function that reverses a list"
   ```
3. While it answers, run `ollama ps` in a second terminal. It should say `100% GPU`. If it says CPU, update the AMD
   driver; if it still says CPU, it works anyway, only slower.

## 2. Run the generator
From the `asm_alpha8_dev16` folder (Python 3.9 or newer; nothing to install):
```
python tools/generate_pairs.py --model qwen2.5-coder:7b --out pairs.jsonl --limit 20
```
That is a 20-pair test. Look at the last lines it prints (accepted / rejected). Then the real run:
```
python tools/generate_pairs.py --model qwen2.5-coder:7b --out pairs.jsonl --per-function 6
```
- About 2,300 requests (392 functions from 7 projects, 6 kinds of bug each). On an RX 7600 that should take a few
  hours; leave it overnight.
- Stop any time with Ctrl+C; run the same command again to continue where it stopped.
- It downloads 6 small source archives from PyPI (checked by SHA-256) into `~/.asm_dev16_cache`.
- It never runs the downloaded code. It only reads it and sends functions to your local model.

## 3. Send the file back
Give me `pairs.jsonl` (attach it in the chat). ASM verifies every pair by running the tests in its sandbox, builds
the training data, trains, and reports results against the pre-registered rules in
`benchmarks/preregistration/dev16_study.md`.

## What gets recorded per pair
Project, version and archive hash; the function and its file hash; the bug kind asked for; the model name and digest;
the prompt hash, seed and temperature; the model's buggy version; whether it passed the local checks and why not.
Nothing about you or your computer is recorded.
