"""DEV31 review probes: a distinguishing input on the developer's fixed tree and on ASM's patched tree of a fresh real bug,
in the bug's own Python 3.8 virtualenv and inside ASM's sandbox (dev29_probes.run).
Usage: python benchmarks/dev31_probes.py <work_dir>
"""
import sys
from pathlib import Path

import dev29_probes

PROBES = {
    ("scrapy", 9): ("from scrapy.mail import MailSender\ngot = {}\n"
                    "def cb(**kw):\n    got.update(to=kw['to'], cc=kw['cc'], To=kw['msg']['To'], Cc=kw['msg']['Cc'])\n"
                    "MailSender(debug=True).send(to='a@example.com', subject='s', body='b', cc='c@example.com', _callback=cb)\n"
                    "print(got)"),
    ("fastapi", 4): ("from fastapi import Depends, FastAPI\napp = FastAPI()\n"
                     "def sub(q: str = None):\n    return q\n"
                     "def dep(s=Depends(sub), page: int = 1):\n    return s\n"
                     "@app.get('/items')\ndef items(d=Depends(dep), x: int = 0):\n    return d\n"
                     "print(sorted(p['name'] for p in app.openapi()['paths']['/items']['get']['parameters']))"),
}

if __name__ == "__main__":
    dev29_probes.run(Path(sys.argv[1]), PROBES)
