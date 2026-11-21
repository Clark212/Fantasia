import argparse
from pathlib import Path
from migrate import copy_database
from asm import ASMEngine, ASMConfig, available_language_cores, __version__


HELP = """
Commands:
  /goal <text>      add a persistent goal
  /stats            show graph/memory size
  /state            show current workspace
  /predict          show predicted next concepts
  /infer <text>     infer a learned rule for unseen input
  /parse <text>     show relations, polarity, and unsupported syntax
  /expand <text>    expand a problem through associations/analogies
  /belief A | P     inspect what agent A believes about proposition P
  /compare A | P    compare world evidence with agent A's belief
  /emotion <text>   infer learned emotion labels
  /concepts         inspect self-created latent concepts
  /relations        inspect self-discovered relation prototypes
  /relation <text>  query the machine-created relation ontology
  /self             inspect ASM's own internal/self model
  /attention        inspect current seismic focus
  /language         inspect active language-cortex backend
  /eventmemory      inspect typed semantic-event memory
  /world            inspect current v0.3 world-state slots
  /transitions      inspect recent non-causal transition evidence
  /mechanisms       inspect learned mechanisms + seismic scheduler
  /history          show recent conversation turns
  /debug on|off     show/hide ASM internal processing after replies
  /embed <text>     inspect language-core embedding dimensions/vector head
  /generate <text>  inspect legacy language-backend generation
  /nested A>B | P   query nested belief A believes B believes P
  /outcome T | S | success/failure  report strategy result
  /strategies T | A,B,C            rank strategies for task T
  /quit             save and exit

Anything else is treated as a new event.
"""


def short_name(concept: str) -> str:
    return (
        concept
        if len(concept) <= 52
        else concept[:49] + "..."
    )


def main():
    parser = argparse.ArgumentParser(description="ASM offline pattern-learning experiment")
    parser.add_argument("--db", type=Path, default=Path("asm_state.db"))
    parser.add_argument("--empty", action="store_true", help="Do not seed a new database from the bundled demo.")
    parser.add_argument("--import-db", type=Path, help="Copy an existing ASM database; never overwrites --db.")
    parser.add_argument(
        "--language-core",
        choices=available_language_cores(),
        help="Language backend. Default: recurrent. Use rwkv7 with --rwkv-model for an external RWKV-7 checkpoint.",
    )
    parser.add_argument("--rwkv-model", type=Path, help="Local RWKV-7 .pth checkpoint path.")
    parser.add_argument("--rwkv-strategy", help="RWKV runtime strategy, e.g. 'cpu fp32' or 'cuda fp16'.")
    parser.add_argument("--writer", choices=["recurrent", "hybrid"], default="recurrent")
    parser.add_argument("--writer-style", choices=["brief", "full"], default="full")
    args = parser.parse_args()
    if args.import_db:
        copy_database(args.import_db, args.db)
    elif not args.db.exists() and not args.empty:
        demo = Path(__file__).resolve().parent / "asm_v030a11_trained.db"
        if demo.exists():
            copy_database(demo, args.db)
    cfg = ASMConfig(writer_backend=args.writer, writer_style=args.writer_style)
    if args.language_core:
        cfg.language_core_backend = args.language_core
    if args.rwkv_model:
        cfg.rwkv7_model_path = str(args.rwkv_model)
        if not args.language_core:
            cfg.language_core_backend = "rwkv7"
    if args.rwkv_strategy:
        cfg.rwkv7_strategy = args.rwkv_strategy
    asm = ASMEngine(args.db, config=cfg)
    debug = False
    print(f"ASM — Artificial Seismic Machine v{__version__}")
    print("Conversation mode is active. Type normally to chat; use /debug on for internals.")
    print(HELP)

    try:
        while True:
            try:
                text = input("\nimpulse> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue

            if text == "/quit":
                break

            if text == "/stats":
                print(asm.stats())
                continue

            if text == "/state":
                print("\nCurrent workspace:")
                for concept, activation in asm.field.workspace():
                    print(
                        f"  {activation:+.3f}  "
                        f"{short_name(concept)}"
                    )
                continue

            if text == "/predict":
                print("\nPredicted next active concepts:")
                for concept, score in sorted(
                    asm.last_prediction.items(),
                    key=lambda kv: kv[1],
                    reverse=True,
                )[:12]:
                    print(
                        f"  {score:.3f}  "
                        f"{short_name(concept)}"
                    )
                continue


            if text == "/self":
                print(asm.self_state())
                continue

            if text == "/attention":
                print(asm.attention_state())
                continue

            if text == "/language":
                print(asm.language_core_status())
                continue

            if text == "/eventmemory":
                print(asm.event_memory.stats())
                continue

            if text == "/world":
                rows = asm.world_state(limit=24)
                if not rows:
                    print("No explicit world-state slots yet.")
                for row in rows:
                    print(row)
                continue

            if text == "/transitions":
                rows = asm.world_transitions(limit=24)
                if not rows:
                    print("No world-state transition evidence yet.")
                for row in rows:
                    print(row)
                continue

            if text == "/history":
                print(asm.conversation_state())
                continue

            if text.startswith("/debug"):
                arg = text[len("/debug"):].strip().lower()
                if arg not in {"on", "off"}:
                    print("Use: /debug on or /debug off")
                    continue
                debug = arg == "on"
                print(f"Debug {'enabled' if debug else 'disabled'}.")
                continue

            if text == "/embed":
                print("Use: /embed <text>")
                continue

            if text.startswith("/embed "):
                vector = asm.embed_text(text[len("/embed "):].strip())
                print({"dims": len(vector), "head": vector[:12]})
                continue

            if text.startswith("/generate"):
                instruction = text[len("/generate"):].strip()
                print(asm.generate_text(instruction))
                continue

            if text.startswith("/nested "):
                payload = text[len("/nested "):].strip()
                if "|" not in payload:
                    print("Use: /nested Alice>Bob | proposition")
                    continue
                path_raw, proposition = [
                    x.strip() for x in payload.split("|", 1)
                ]
                path = [x.strip() for x in path_raw.split(">") if x.strip()]
                print(asm.nested_belief(path, proposition))
                continue

            if text.startswith("/outcome "):
                payload = text[len("/outcome "):].strip()
                parts = [x.strip() for x in payload.split("|")]
                if len(parts) != 3:
                    print("Use: /outcome task | strategy | success/failure")
                    continue
                task, strategy, result = parts
                success = result.lower() in {"success", "pass", "true", "1"}
                print(
                    asm.report_strategy_outcome(
                        task,
                        strategy,
                        success,
                    )
                )
                continue

            if text.startswith("/strategies "):
                payload = text[len("/strategies "):].strip()
                if "|" not in payload:
                    print("Use: /strategies task | strategy_a,strategy_b")
                    continue
                task, options = [x.strip() for x in payload.split("|", 1)]
                candidates = [x.strip() for x in options.split(",") if x.strip()]
                print(asm.choose_strategy(task, candidates))
                continue

            if text == "/relations":
                rows = asm.discovered_relations()
                if not rows:
                    print("No promoted self-discovered relations yet.")
                for row in rows[:16]:
                    print(
                        f"  {row['id']} support={row['support']:.1f} "
                        f"strength={row['strength']:.3f} "
                        f"generic={row.get('generic_support', 0):.1f} "
                        f"connectors={row['prototype']['connector'][:6]}"
                    )
                continue

            if text.startswith("/relation "):
                query = text[len("/relation "):].strip()
                print(asm.infer_discovered_relation(query))
                continue

            if text == "/concepts":
                rows = asm.latent_concepts()
                if not rows:
                    print("No promoted latent concepts yet.")
                for row in rows[:12]:
                    print(
                        f"  {row['id']} support={row['support']} "
                        f"prototype={row['prototype'][:8]}"
                    )
                continue

            if text.startswith("/belief "):
                payload = text[len("/belief "):].strip()
                if "|" not in payload:
                    print("Use: /belief Agent | proposition")
                    continue
                holder, proposition = [part.strip() for part in payload.split("|", 1)]
                print(asm.belief(holder, proposition))
                continue

            if text.startswith("/compare "):
                payload = text[len("/compare "):].strip()
                if "|" not in payload:
                    print("Use: /compare Agent | proposition")
                    continue
                holder, proposition = [part.strip() for part in payload.split("|", 1)]
                print(asm.compare_belief(holder, proposition))
                continue

            if text.startswith("/emotion "):
                query = text[len("/emotion "):].strip()
                ranked = asm.infer_emotion(query)
                if not ranked:
                    print("No learned emotion prototype is confident enough.")
                else:
                    for item in ranked:
                        print(
                            f"  {item['score']:.3f}  {item['emotion']} "
                            f"from {item['examples']} examples "
                            f"matches={item['matched_features'][:5]}"
                        )
                continue

            if text.startswith("/parse "):
                parsed = asm.parse_open(text[len("/parse "):])
                for r in parsed["relations"]:
                    print(
                        f"  {r['left']} --{r['key']}--> {r['right']} "
                        f"confidence={r['confidence']:.3f}"
                    )
                print(
                    f"supported={parsed['supported']}; "
                    f"source={parsed['source']}; "
                    f"confidence={parsed['confidence']:.3f}; "
                    f"warnings={parsed['warnings']}"
                )
                continue

            if text.startswith("/expand "):
                query = text[len("/expand "):].strip()
                expansion = asm.expand_problem(query)
                prediction = expansion["prediction"]
                print(f"prediction: {prediction['status']} — {prediction['relation'] or 'abstained'}")
                print(f"  {prediction['reason']}")
                if prediction["status"] == "predicted":
                    print(f"  evidence score={prediction['score']:.3f}, support={prediction['support']}; not a probability")
                print("structure:")
                print(f"  relations: {expansion['frame']['relations']}")
                print(f"  cues: {expansion['frame']['cues']}")

                if expansion["analogies"]:
                    print("analogies:")
                    for item in expansion["analogies"][:4]:
                        print(
                            f"  {item['score']:.3f}  "
                            f"{item['text'][:90]}"
                        )

                if expansion["abstractions"]:
                    print("abstractions:")
                    for item in expansion["abstractions"][:4]:
                        print(
                            f"  {item['score']:.3f}  "
                            f"{item['id']} "
                            f"support={item['support']}"
                        )

                if expansion["hypotheses"]:
                    print("hypotheses:")
                    for item in expansion["hypotheses"][:6]:
                        print(
                            f"  {item['score']:.3f}  "
                            f"{item['hypothesis']}"
                        )
                        for evidence in item["evidence"][:2]:
                            print(f"      <- {evidence}")
                else:
                    print("No strong hypotheses yet.")
                continue

            if text.startswith("/infer "):
                query = text[len("/infer "):].strip()
                predictions = asm.infer_rule(query)
                if not predictions:
                    print("No confident learned rule.")
                else:
                    print("generalization:")
                    for outcome, confidence in predictions:
                        print(f"  {confidence:.3f}  {outcome}")
                continue

            if text.startswith("/goal "):
                goal = text[len("/goal "):].strip()
                asm.add_goal(goal)
                print(f"Goal stored: {goal}")
                continue

            if text.startswith("/"):
                print("Unknown or incomplete command. Type one of the commands shown above.")
                continue

            result = asm.chat(text)
            print(f"ASM> {result['reply']}")

            if debug:
                print(
                    f"  [magnitude={result['magnitude']:.3f} "
                    f"surprise={result['surprise']:.3f} "
                    f"consolidation={result.get('consolidation', {}).get('reason', 'n/a')}]"
                )
                act = result.get("conversation", {}).get("act", {})
                if act:
                    print(
                        f"  [dialogue={act.get('label')} "
                        f"confidence={act.get('confidence', 0.0):.3f} "
                        f"source={act.get('source')}]"
                    )
                if result.get("recalled"):
                    print("  [aftershocks]")
                    for item in result["recalled"][:3]:
                        print(
                            f"    #{item['id']} {item['relevance']:.3f} "
                            f"{item.get('retrieval_source', 'lexical')}: {item['text'][:90]}"
                        )
                print("  [workspace]")
                for concept, activation in result["workspace"][:8]:
                    print(f"    {activation:+.3f} {short_name(concept)}")

    finally:
        asm.close()
        print("ASM state saved.")


if __name__ == "__main__":
    main()
