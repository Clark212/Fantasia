# DEV31 fresh real bugs: every accepted patch read against the developer's fix (pre-registered G31-A)

Two of the 75 fresh bugs ended `resolved`, both in the control and in the learned arm. The two arms made byte-identical
patches, accepted in phase 1 or 2 before phase 3 could run. No bug was resolved by the learned arm alone, so the time
control (`control_long`, 300 s) ran on no bug (`dev31_time_control.jsonl`).

I read each patch against the developer's diff; both are stored in the raw records. A probe then ran on the developer's
fixed tree and on ASM's patched tree, in the bug's own Python 3.8 virtualenv inside ASM's sandbox
(`benchmarks/dev31_probes.py` → `probes.jsonl`). The developer's fixed test files pass on both patched trees.

| bug | arms | ASM's edit (family) | oracle | **verdict** | basis |
|---|---|---|---|---|---|
| fastapi-4 | both | `sub_dependant.cache_key in visited` → `not in visited` in `get_flat_dependant` (single_site) | unknown (no replayable calls) | **wrong** | the developer de-duplicates the OpenAPI parameters by name, in `get_openapi_path`. ASM's patch skips every sub-dependency on its first visit instead of on its repeats, so sub-dependencies are no longer flattened. Probe: a route whose dependency has a sub-dependency documents `['page', 'q', 'x']` when fixed and `['x']` when patched |
| scrapy-9 | both | `try/except AttributeError: pass` around `rcpts.extend(cc)` in `MailSender.send` (try_except) | unknown (no replayable calls) | **wrong** | the developer turns `to` and `cc` into lists (`arg_to_iter`), so a string is one address. ASM's patch swallows the error and keeps them as strings. Probe: `send(to='a@example.com', cc='c@example.com')` gives the header `To: a@example.com` when fixed and `To: a, @, e, x, a, m, p, l, e, ., c, o, m` when patched |

## Totals
| | control | learned | control_long |
|---|---|---|---|
| accepted patches | 2 | 2 (the same two) | — (no bug qualified) |
| correct | 0 | 0 | — |
| wrong | 2 | 2 | — |

- **G31-A, person-read:**
  - **C1 learned repairs:** 0 bugs correct with the learned arm alone; 2 needed. **Not met.**
  - **C2 no loss:** 0 control-correct bugs lost. Met.
  - **C3 safety:** learned wrong patches 2, against the control's 2 + 1 allowed. Met.
  - **C4 the clock holds:** the longest learned run took 298 s, within 360. Met.

  **G31-A is not passed.**
- **Not accepted, reported:** in scrapy-32 the learned arm ended `partial` with a learned step. It replaced
  `verifyClass(ISpiderLoader, loader_cls)` with `KeyError(ISpiderLoader, loader_cls)`, an exception object that is never
  raised. That disables the check; the content came from the failure message. The developer's fix is elsewhere
  (`CrawlerProcess.__init__` uses `self.settings`).
- **The oracle** could not judge either accepted patch: their functions have no replayable calls in the original
  program's tests. The probes decided.

## Probes (`probes.jsonl`; each bug's virtualenv, inside `run_python_worker`, warnings ignored)
```
scrapy-9   MailSender(debug=True).send(to='a@example.com', subject='s', body='b', cc='c@example.com', _callback=cb)
           fixed   {'to': ['a@example.com'], 'cc': ['c@example.com'], 'To': 'a@example.com', 'Cc': 'c@example.com'}
           patched {'to': 'a@example.com', 'cc': 'c@example.com', 'To': 'a, @, e, x, a, m, p, l, e, ., c, o, m', 'Cc': 'c, @, ...'}
fastapi-4  parameters of GET /items, where items(d=Depends(dep), x) and dep(s=Depends(sub), page) and sub(q)
           fixed   ['page', 'q', 'x']
           patched ['x']
```
