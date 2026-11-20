# RWKV-7 backend setup — alpha.5.2

ASM can use an optional RWKV-7 language backend. Third-party model weights are not bundled.

1. Install an RWKV runtime compatible with your checkpoint.
2. Obtain a local RWKV-7 checkpoint/tokenizer.
3. Start ASM with, for example:

```bash
python main.py --language-core rwkv7 --rwkv-model /path/to/model.pth --rwkv-strategy "cpu fp32"
```

Inside ASM, `/language` should report the backend as ready before you rely on it.

## Trust boundary

Alpha.5.2 does not let RWKV directly mutate ASM's persistent beliefs. The backend can emit constrained JSON `LanguageProposal` objects. ASM then validates the schema, finite numeric ranges, proposal type, and configured acceptance gates before persistence.

The generation context is bounded and may include current focus, self state, agent beliefs, active goals, world state, relevant memories, and workspace information.

The constrained extractor/parser has synthetic contract tests in this release, but **real extraction accuracy on unseen natural language is not claimed** because no RWKV weights are bundled or certified by these tests.

If the runtime or checkpoint fails to load, ASM falls back to its non-RWKV language path rather than treating the failed backend as successful.
