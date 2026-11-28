# ASM v0.2 Language Cortex API

The language cortex is a replaceable interface. It is **not** the owner of ASM's beliefs or memory.

## Contract

A backend implements `LanguageCore`:

```python
read(text) -> LanguageReadResult
generate(state, instruction="") -> LanguageGenerationResult
capabilities() -> dict
health() -> dict
```

`read()` can return `LanguageProposal` objects. Supported proposal kinds in alpha.1 are:

- `belief`
- `nested_belief`
- `drive`
- `self_outcome`

Every proposal has a confidence. ASM applies its own `language_core_min_confidence` gate before a proposal may update cognition.

## Important boundary

A neural core may propose:

```text
"Alice believes the gate is shut" confidence=0.84
```

ASM then decides whether to accept and how to revise its persistent belief state. The backend never writes directly to the database.

## Future RWKV/Mamba backend

A later adapter should:

1. load a frozen local recurrent checkpoint,
2. produce an embedding/state vector,
3. extract structured proposals,
4. generate language from an ASM-provided cognitive state,
5. keep all new factual learning inside ASM unless explicitly training the language core.

`CallableLanguageCore` is included to prototype this without changing `ASMEngine`.
