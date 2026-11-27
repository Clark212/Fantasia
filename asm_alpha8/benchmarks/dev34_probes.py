"""DEV34 review probes (dev33_probes.main with DEV34's records): a distinguishing input on the developer's fixed tree and
on the arm's patched tree, in the bug's own virtualenv inside ASM's sandbox.
Usage: python benchmarks/dev34_probes.py <work_dir>
"""
import dev33_probes

TRY = dev33_probes.TRY
PROBES = {
    (("pycparser", 5), ("checked",)): ("from pycparser import c_parser\n" + TRY +
        "def p(s):\n    try:\n        return type(c_parser.CParser().parse(s)).__name__\n    except BaseException as e:\n        return f'{type(e).__name__}: {e}'\n"
        "print([p(s) for s in ['int f() { return 1; }', 'int f() { return 1; } }', '}', 'int x; }}', 'void g(void) { { } } }', 'int a; } int b;']])"),
}

if __name__ == "__main__":
    dev33_probes.main(PROBES, "dev34_*of*.jsonl")
