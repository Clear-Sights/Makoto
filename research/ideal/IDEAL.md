# Makoto by the Ideal technique (Hub-Reborn `TECHNIQUES.md`, Ideal, at 5039d98)

Owner, 2026-11-13: "Read the ideal technique in hub and apply it". Written while the 6.2.2 run was in progress; it uses no result of that run. Every number is measured (source named) unless marked projected.

## 1 to 4. Need, class, one piece per step
**Goal:** the final answer ships changes that work, and it is known that they work.

| piece | what must be known | class | got when |
|---|---|---|---|
| A | the tree at session start | pulled (file sizes and times) | session start |
| B | which file depends on which | pulled (the files' text) | session start; again for a changed file |
| C | what the session changed, and what that demands (C with B) | collected (a deterministic compare) | after any tool call |
| D | which run covers the demanded set | collected (read from B) | with C |
| E | whether that run succeeds, and its error if not | **collected** (running a program is deterministic) | once C is stable |
| F | the fix, when E fails | **created** (the model) | after E |

- C and "what it demands" can only be got together, so they are one piece.
- Nothing else is needed. Pieces that earlier versions got are not on any path to the goal: names seen, online fetches, read-before-edit, a journal of events.

## 5. The critical path
input, change (created), E, F only if E fails, final answer. A, B, C and D need nothing from the model, so they run beside it.

## 6 and 7. Mechanism and leverage, as it stands in 6.2.1
| step | mechanism | #1 gets its piece by its class | #2 waits only for what it reads |
|---|---|---|---|
| A, B | the map, built in the session-start hook | yes | yes |
| C, D | compared at the final answer, and after edit tools | yes at the final answer; **no** for a change made through the shell | yes |
| E | **the model runs the program**, told by the note or forced by the hold | **no**: a collected piece is got by the creating actor, at the price of a model turn | **no**: it waits for the model to choose to run |
| F | the model | yes | fed the error only after its own run |

**Leverage:** the note tells the model *that* a run is needed. It doesn't give the model what it would otherwise have to find, which is the run's result.

## 8. Measure
| | default (no Makoto) | what stands (6.2.1) | ideal |
|---|---|---|---|
| pass, Haiku, unrun and sigchange (n 80) | 51 of 80 (64 %) | 73 of 80 (91 %) | about 95 % (projected) |
| cost, ratio to default | 1 | 1.33 | about 1.12 (projected) |
| pass, Sonnet, same families (n 80) | 44 of 80 (55 %) | 78 of 80 (98 %) | about 98 % (projected) |
| cost, Sonnet | 1 | 1.57 to 1.68 | about 1.15 (projected) |

Sources: `research/v621/RESULTS.md`, `research/claims/RESULTS.md`.

- **Ideal pass:** every failure a run reveals is fixed. What remains is the model abandoning the goal, or making no edit: 4 of the 6 failures traced in `research/v621/RULES.md`.
- **Ideal cost:** E costs no model turn, so the only added cost is F, in the share of runs whose change is broken. That share is about a third; one fix turn is about a third of a run.
- **Distance bridged:** on pass, about 87 % of the way from default to ideal (Haiku). On cost, the gap is the whole 0.21 to 0.5 above the ideal.
- **Where the cost gap traces:** one departure, step E. Makoto makes the model do a collected step. Each run pays a turn for the run (Haiku, by the note), or a thrown-away final answer plus a turn (Sonnet, by the hold).

The 6.2.2 change repairs C and D for shell edits. It does not touch E.

## The one change the technique asks for
- **Makoto gets E itself, beside the model.**
  - Once a change is on the map, it runs the covering program in an isolated copy: no network, and gated by the map's outward links.
  - A result counts only for the tree it read. If the tree changed since, the result is dropped and the run repeated.
- **Leverage, in the most immediate form:** the result goes to the model.
  - A pass says nothing and stamps the nodes, so the final answer is admitted with no turn spent.
  - A failure puts the error itself in the note, or in the hold if the model is already answering.
- **Fallback:** where Makoto cannot run the program (it needs arguments, is not isolable, or times out), 6.2.2's note and hold stand.

**Why this is not the earlier probe:** `research/set_probe/RESULTS.md` found no gain from a probe. That one ran only at the final answer and gave no result back until then, so a failure still cost the thrown-away answer. This one runs as soon as the change exists.

## 9. Predict (projected; to be fixed in a round's rules before any run)
- **Haiku:** pass stays within 2 tasks of 6.2.2's; cost falls from about 1.33 to between 1.10 and 1.20.
- **Sonnet:** pass stays; holds fall from 1.0 per run to under 0.4; cost falls from about 1.6 to between 1.10 and 1.25.
- **A miss** is an implementation fault, to be traced to the line that departs from its rule.

## Named limits
- **What E can see:** only what the covering program exercises. A wrong result that raises no error is not seen.
- **The fallback:** a program that cannot run with no argument, or reaches an outward library, keeps 6.2.2's cost.
- **Trust:** running project code inside a hook, even isolated, is a trust the user must grant. It should be a setting, off unless set.
