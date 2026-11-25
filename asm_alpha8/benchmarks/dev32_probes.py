"""DEV32 review probes: a distinguishing input on the developer's fixed tree and on ASM's patched tree of a fresh real bug,
in the bug's own Python 3.11 virtualenv and inside ASM's sandbox (dev29_probes.run). Every accepted patch has one; SECOND holds
the follow-up probes for the patches the first one did not tell apart.
Usage: python benchmarks/dev32_probes.py <work_dir>
"""
import sys
from pathlib import Path

import dev29_probes

TRY = "def t(f, *a):\n    try:\n        return f(*a)\n    except Exception as e:\n        return type(e).__name__\n"
INFLECT = "import inflect\np = inflect.engine()\n"
PROBES = {
    ("astroid", 1): ("import astroid\n" + TRY +
                     "print([t(lambda s: [type(x).__name__ for x in astroid.extract_node(s).inferred()], s)"
                     " for s in ['unknown_name.format(1)', '\"{}\".format(1)', 'str(1).format(2)']])"),
    ("astroid", 4): ("import astroid\nn = astroid.extract_node('try:\\n    pass\\nexcept UnicodeDecodeError as e:\\n    e.object #@')\n"
                     "print([repr(getattr(x, 'value', x)) for x in n.inferred()])"),
    ("autoflake", 2): ("import autoflake\n" + TRY +
                       "print([t(autoflake.extract_package_name, s) for s in ['import', 'from', 'import os', 'import\\tos', 'from . import x', 'imported = 1']])"),
    ("marko", 4): ("import marko\nfrom marko.md_renderer import MarkdownRenderer\nsrc = ['- a\\n\\n- b\\n', '- a\\n- b\\n', '1. a\\n\\n   b\\n2. c\\n']\n"
                   "print([marko.Markdown(renderer=MarkdownRenderer)(s) for s in src], [marko.convert(s) for s in src])"),
    ("sqlglot", 14): ("import sqlglot\nq = [\"SELECT INTERVAL '1' WEEK\", \"SELECT INTERVAL '2' QUARTER\", \"SELECT INTERVAL '3' DAY\", \"SELECT x + INTERVAL 1 MONTH\"]\n"
                      "print([sqlglot.transpile(s, read=r, write='duckdb')[0] for s in q for r in ('duckdb', 'postgres')])"),
    ("inflect", 2): INFLECT + "print([p.singular_noun(w) for w in ['cats', 'grass', 'glass', 'dogs', 'cat', 'bus', 'moss']])",
    ("inflect", 7): INFLECT + TRY + ("print([t(p.singular_noun, w) for w in ['mothers-in-law', 'mother-in-law', 'cats of the town', 'cat']],"
                                     " [t(p.plural, w) for w in ['mother-in-law', 'cat', 'son of a gun']])"),
    ("inflect", 9): INFLECT + "print([p.plural(w) for w in ['Kennedy', 'Mary', 'day', 'John Kennedy', 'boy', 'Cat', 'baby']])",
    ("jsonpickle", 3): ("import re, jsonpickle\nr = jsonpickle.decode(jsonpickle.encode(re.compile('a+', re.I)))\n"
                        "print(type(r).__name__, getattr(r, 'pattern', r), getattr(r, 'flags', None))"),
    ("markdownify", 4): ("from markdownify import markdownify as md\n"
                         "print([md(s) for s in ['<hn>x</hn>', '<h1>T</h1>', '<h2>a <b>b</b></h2>', '<p>p</p><hn>y</hn>']])"),
    ("rich", 11): ("from rich.segment import Segment\n"
                   "print([[tuple(s.text for s in Segment(w).split_cells(i)) for i in range(5)] for w in ['あいう', 'abc', 'aあb']])"),
    ("rich", 15): ("import io\nfrom rich.console import Console\n"
                   "def out(m, kw):\n    c = Console(markup=m, file=io.StringIO(), width=40, color_system=None)\n    c.print('[bold]x[/bold]', **kw)\n    return c.file.getvalue()\n"
                   "print([out(m, kw) for m in (True, False) for kw in ({}, {'markup': True}, {'markup': False})])"),
    ("soupsieve", 2): ("import soupsieve as sv\n" + TRY +
                       "print([t(lambda s: type(sv.compile(s)).__name__, s) for s in [':unknown', 'div:hover', 'a:contains(x)', 'div:not(.a)', 'p:first-child']])"),
    ("soupsieve", 4): ("import soupsieve as sv\n" + TRY +
                       "print([t(lambda s: sv.compile(s).pattern, s) for s in ['div', 'div /* c */ ', 'div /* a * b */', 'div ']],"
                       " t(lambda: type(sv.compile(sv.compile('div'))).__name__))"),
}

SECOND = {
    ("inflect", 7): ("import inflect\nfrom inflect import Words\np = inflect.engine()\n" + TRY +
                     "print([t(p._handle_long_compounds, Words(w), n) for w in ['pair of scissors', 'men beyond hills', 'mother of god'] for n in (1, 2)],"
                     " [p.plural_noun(w) for w in ['pair of scissors', 'man beyond hills']], [p.singular_noun(w) for w in ['pairs of scissors', 'men beyond hills']])"),
    ("soupsieve", 2): ("import soupsieve as sv\n" + TRY +
                       "print([t(lambda s: type(sv.compile(s)).__name__, s) for s in ['p:nth-child', 'p:is', 'p:not', 'p:contains', ':nth-of-type', ':foo', 'p:lang']])"),
    ("rich", 11): ("import hashlib, itertools\nfrom rich.segment import Segment\n"  # every split of every 1-6 character mix of narrow and wide
                   "ws = [''.join(c) for n in range(1, 7) for c in itertools.product('a\\u3042', repeat=n)]\n"
                   "out = [[s.text for s in Segment(w).split_cells(i)] for w in ws for i in range(14)]\n"
                   "print(len(out), hashlib.sha256(repr(out).encode()).hexdigest()[:16])"),
    ("markdownify", 4): ("from markdownify import MarkdownConverter\n" + TRY +
                         "class C(MarkdownConverter):\n    def convert_b(self, el, text):\n        return '!' + text\n"
                         "print(t(lambda: C().convert('<b>x</b>')), t(lambda: C().convert('<hn>y</hn>')))"),
}

if __name__ == "__main__":
    dev29_probes.run(Path(sys.argv[1]), PROBES)
    dev29_probes.run(Path(sys.argv[1]), SECOND)
