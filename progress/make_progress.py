"""Progress to ASM v1.0.0: regenerate the progress bar, the DEV gate chart and the README section.

Run after every DEV step (add the DEV to progress/progress.json first):
    python3 progress/make_progress.py          # write progress/*.svg and the README section
    python3 progress/make_progress.py --check  # exit 1 if any of them is out of date

Milestones and their names come from ROADMAP.md; what is reached, open and in progress comes from progress.json.
Standard library only; the SVGs have a white card background so they read in GitHub's light and dark themes.
"""
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "progress" / "progress.json"
BAR_SVG = ROOT / "progress" / "progress_to_1.0.0.svg"
DEV_SVG = ROOT / "progress" / "dev_history.svg"
README = ROOT / "README.md"
START, END = "<!-- progress:start -->", "<!-- progress:end -->"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
INK, MUTED, LINE = "#1f2328", "#59636e", "#d0d7de"
COLOR = {"reached": "#2da44e", "in_progress": "#54aeff", "open": "#d4a72c", "not_started": "#eaeef2"}
STAGE_NAMES = {"0.0": "Foundation", "0.1": "Core", "0.2": "Prediction", "0.3": "Concepts", "0.4": "Planning",
               "0.5": "Causal", "0.6": "Meta", "0.7": "Self-model", "0.8": "Language", "0.9": "Multimodal",
               "1.0": "v1.0.0"}


def milestones():
    """[(id, name)] in roadmap order, 0.0.1 ... 0.9.9, then 1.0.0, parsed from ROADMAP.md's milestone lists."""
    out = []
    for para in re.split(r"\n\s*\n", (ROOT / "ROADMAP.md").read_text()):
        flat = " ".join(line.strip() for line in para.splitlines())
        if flat.count(" · ") < 5:  # only the lists of milestones ("0.1.0 Name · 0.1.1 Name · ...")
            continue
        for item in flat.split(" · "):
            m = re.search(r"(\d\.\d\.\d) (.+)$", item.strip())
            if m and m.group(1) != "1.0.0":
                out.append((m.group(1), m.group(2).strip()))
    out.append(("1.0.0", "Artificial Seismic Machine"))
    return out


def status(mid, rm):
    if mid in rm["open"]:
        return "open"
    if mid in rm.get("promoted_in_progress", []):
        return "reached"
    if mid in rm["in_progress"]:
        return "in_progress"
    key = tuple(int(x) for x in mid.split("."))
    return "reached" if key <= tuple(int(x) for x in rm["reached_through"].split(".")) else "not_started"


def summary(data):
    ms = milestones()
    rm = data["roadmap"]
    st = [(mid, name, status(mid, rm)) for mid, name in ms]
    count = {k: sum(1 for *_, s in st if s == k) for k in COLOR}
    nxt = rm.get("next_label") or next((name for mid, name in ms if mid == rm["next"]), "")
    return ms, st, count, nxt


def svg_text(x, y, s, size=12, weight="normal", fill=INK, anchor="start"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>')


def bar_svg(data):
    ms, st, count, nxt = summary(data)
    rm, latest = data["roadmap"], data["devs"][-1]["dev"]
    w, x0, y0, h = 920, 20, 92, 30
    groups = []
    for mid, name, s in st:
        if not groups or groups[-1][0] != mid[:3]:
            groups.append((mid[:3], []))
        groups[-1][1].append((mid, name, s))
    gap_in, gap_out = 2, 8
    cell = (w - 2 * x0 - gap_out * (len(groups) - 1) - gap_in * (len(st) - len(groups))) / len(st)
    total = len(st)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="214" viewBox="0 0 {w} 214" role="img" '
           f'aria-label="ASM progress to v1.0.0: {count["reached"]} of {total} roadmap milestones reached">',
           f'<rect x="0.5" y="0.5" width="{w - 1}" height="213" rx="8" fill="#ffffff" stroke="{LINE}"/>',
           svg_text(x0, 34, "ASM — progress to v1.0.0", 18, "600"),
           svg_text(x0, 58, f"{rm['current']} · latest step {latest} · {count['reached']} of {total} roadmap "
                            f"milestones reached ({round(100 * count['reached'] / total)}%)", 13, fill=MUTED),
           svg_text(x0, 77, f"In development: {', '.join(rm['in_progress'])} ({rm['in_progress_note']}) · "
                            f"next to promote: {rm['next']} {nxt}", 13, fill=MUTED)]
    x = x0
    for gid, cells in groups:
        gx = x
        for mid, name, s in cells:
            stroke = f' stroke="{INK}" stroke-width="1.5"' if mid == rm["next"] else ""
            out.append(f'<rect x="{x:.2f}" y="{y0}" width="{cell:.2f}" height="{h}" rx="1.5" fill="{COLOR[s]}"{stroke}>'
                       f'<title>{escape(mid)} {escape(name)}: {s.replace("_", " ")}</title></rect>')
            x += cell + gap_in
        x += gap_out - gap_in
        mid_x = (gx + x - gap_out) / 2
        out.append(svg_text(mid_x, y0 + h + 16, gid, 11, "600", anchor="middle"))
        out.append(svg_text(mid_x, y0 + h + 29, STAGE_NAMES.get(gid, ""), 10, fill=MUTED, anchor="middle"))
    lx, ly = x0, 178
    for key, label in (("reached", f"reached ({count['reached']})"),
                       ("in_progress", f"in progress, not promoted ({count['in_progress']})"),
                       ("open", f"open: not yet shown ({count['open']})"),
                       ("not_started", f"not started ({count['not_started']})")):
        out.append(f'<rect x="{lx}" y="{ly - 10}" width="12" height="12" rx="2" fill="{COLOR[key]}" stroke="{LINE}"/>')
        out.append(svg_text(lx + 17, ly, label, 12))
        lx += 26 + 7 * len(label)
    out.append(f'<rect x="{lx}" y="{ly - 10}" width="12" height="12" rx="2" fill="{COLOR["in_progress"]}" '
               f'stroke="{INK}" stroke-width="1.5"/>')
    out.append(svg_text(lx + 17, ly, f"next: {rm['next']}", 12))
    out.append(svg_text(x0, 202, "Position on the roadmap, not effort or time: the later stages include open research "
                                 "problems. Counting rule: progress/progress.json.", 10.5, fill=MUTED))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def clip(s, n):
    """s cut to at most n characters at a word boundary, with an ellipsis when cut."""
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0] + "…"


def dev_outcome(d):
    """(fraction of the gate reached, colour, label)."""
    if d["kind"] == "passed":
        return 1.0, COLOR["reached"], "gate passed"
    if d["kind"] == "not_run":
        return 0.0, "#afb8c1", "not run"
    v, n = d["value_reached"], d["needed"]
    ok = d.get("passed", v >= n)  # `passed: false` with `why`: the count was reached but another criterion of the gate failed
    why = f" ({d['why']})" if not ok and d.get("why") else ""
    return min(v / n, 1.0), (COLOR["reached"] if ok else "#cf222e"), f"{v} of {n} needed · {'passed' if ok else 'not passed'}{why}"


def dev_svg(data):
    devs = data["devs"]
    w, x0, row, top = 920, 20, 46, 86
    bx, bw = 470, 260
    h = top + row * len(devs) + 46
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
           f'aria-label="Each DEV step and how much of its pre-registered gate it reached">',
           f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="8" fill="#ffffff" stroke="{LINE}"/>',
           svg_text(x0, 34, "Each DEV and its pre-registered gate", 18, "600"),
           svg_text(x0, 56, "The bar is the share of the gate's threshold reached; a gate passed fills it. "
                            "A version moves only when a pre-registered gate passes.", 13, fill=MUTED),
           svg_text(bx, top - 10, "0", 10, fill=MUTED, anchor="middle"),
           svg_text(bx + bw, top - 10, "gate", 10, "600", fill=MUTED, anchor="middle")]
    for i, d in enumerate(devs):
        y = top + i * row
        frac, col, label = dev_outcome(d)
        if i % 2 == 0:
            out.append(f'<rect x="8" y="{y}" width="{w - 16}" height="{row}" rx="4" fill="#f6f8fa"/>')
        out.append(svg_text(x0, y + 19, d["dev"], 13, "600"))
        out.append(svg_text(x0 + 62, y + 19, d["title"], 13))
        out.append(svg_text(x0 + 62, y + 36, clip(f"{d['date']} · {d['gate']}", 64), 10.5, fill=MUTED))
        out.append(f'<rect x="{bx}" y="{y + 15}" width="{bw}" height="14" rx="3" fill="#eaeef2"/>')
        if frac > 0:
            out.append(f'<rect x="{bx}" y="{y + 15}" width="{bw * frac:.1f}" height="14" rx="3" fill="{col}"/>')
        out.append(svg_text(bx + bw + 14, y + 26, label, 12, "600" if frac >= 1 else "normal",
                            fill=col if d["kind"] != "not_run" else MUTED))
    out.append(f'<line x1="{bx + bw}" y1="{top - 4}" x2="{bx + bw}" y2="{top + row * len(devs)}" stroke="{INK}" '
               f'stroke-width="1" stroke-dasharray="3,3"/>')
    promoted = [d["dev"] for d in devs if d.get("promoted")]
    out.append(svg_text(x0, h - 18, f"Promoted: {', '.join(promoted) if promoted else 'none'}. "
                                    f"Version after the latest DEV: {data['roadmap']['current']}.", 12, fill=MUTED))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def readme_section(data):
    ms, st, count, nxt = summary(data)
    rm, total = data["roadmap"], len(st)
    cells = {k: round(50 * v / total) for k, v in count.items()}
    active = max(cells["in_progress"] + cells["open"], 1 if count["in_progress"] + count["open"] else 0)
    text_bar = "█" * cells["reached"] + "▓" * active
    text_bar += "░" * (50 - len(text_bar))
    lines = [START, "<!-- generated by progress/make_progress.py from progress/progress.json and ROADMAP.md; "
                    "do not edit by hand -->", "## Progress to v1.0.0", "",
             f"**{rm['current']} · latest step {data['devs'][-1]['dev']} · {count['reached']} of {total} roadmap "
             f"milestones reached ({round(100 * count['reached'] / total)}%)**", "",
             f"`{text_bar}` {round(100 * count['reached'] / total)}%", "",
             f"![Progress to v1.0.0](progress/{BAR_SVG.name})", "",
             f"- Reached: {count['reached']} (0.0.1–{rm['reached_through']}: {rm['reached_rule']}).",
             f"- In development: {', '.join(rm['in_progress'])} ({rm['in_progress_note']}). "
             f"Next to promote: **{rm['next']} {nxt}**.",
             *[f"- Open: {mid}, {why}." for mid, why in rm["open"].items()],
             f"- Not started: {count['not_started']} (everything after {rm['in_progress'][-1]}).",
             *([f"- Alpha 8 plan toward {data['alpha8_plan']['target']}: {data['alpha8_plan']['validated']} of "
                f"{data['alpha8_plan']['targets']} targets validated"
                + (f" ({data['alpha8_plan']['evidence_note']})" if data["alpha8_plan"].get("evidence_note") else "")
                + f"; what exists for each: [ROADMAP.md]({data['alpha8_plan']['details']})."]
               if "alpha8_plan" in data else []), "",
             f"![Each DEV and its pre-registered gate](progress/{DEV_SVG.name})", "",
             "| DEV | date | pre-registered gate | result | promoted |", "|---|---|---|---|---|"]
    for d in reversed(data["devs"]):
        _, _, label = dev_outcome(d)
        result = d.get("result") or f"{label} (of {d['of']})"
        lines.append(f"| [{d['dev']}]({d['report']}) {d['title']} | {d['date']} | {d['gate']} | {result} | "
                     f"{'yes' if d.get('promoted') else 'no'} |")
    lines += ["", "This is a position on the roadmap, not effort or time: milestones are not equal work, and several "
                  "later stages are open research problems ([ROADMAP.md](ROADMAP.md)). Updated after every DEV step.",
              END]
    return "\n".join(lines)


def main():
    data = json.loads(DATA.read_text())
    want = {BAR_SVG: bar_svg(data), DEV_SVG: dev_svg(data)}
    readme = README.read_text() if README.exists() else "# Fantasia\n"
    section = readme_section(data)
    if START in readme and END in readme:
        new_readme = readme[:readme.index(START)] + section + readme[readme.index(END) + len(END):]
    else:
        new_readme = readme.rstrip("\n") + "\n\n" + section + "\n"
    want[README] = new_readme
    stale = [p for p, s in want.items() if not p.exists() or p.read_text() != s]
    if "--check" in sys.argv:
        for p in stale:
            print(f"out of date: {p.relative_to(ROOT)}")
        sys.exit(1 if stale else 0)
    for p, s in want.items():
        p.write_text(s)
    _, _, count, _ = summary(data)
    print(f"{sum(count.values())} milestones: " + ", ".join(f"{k} {v}" for k, v in count.items())
          + f"; {len(data['devs'])} DEVs; wrote {', '.join(str(p.relative_to(ROOT)) for p in want)}")


if __name__ == "__main__":
    main()
