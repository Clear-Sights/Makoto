This is a failing, conservative reconstruction, not a completed final-program mesh.

Run `PYTHONDONTWRITEBYTECODE=1 python3 mesh/check.py` and
`PYTHONDONTWRITEBYTECODE=1 python3 mesh/plants.py`. Neither executes runtime hooks.
Extraction is `PYTHONDONTWRITEBYTECODE=1 python3 mesh/types.py`.

Ports use `slot#port` to avoid ambiguity with dots in lexical Python names.
Input/output cells are JSON port-to-type maps. UNRESOLVED is an absence marker,
not an exact type, and always fails. EMPTY identifies unproven implementation
or environment bindings; foreign functions are not silently assumed correct.
Unit is the singleton invocation/completion shape; it does not carry payloads.
Literal arguments and source annotations are extracted mechanically. Bare
collections, callback dispatch, imports through importlib, object methods,
stdlib signatures without exact annotations, effects and expression dataflow
remain proof obligations. Thus current output does NOT meet the exact-type bar.
No OCaml, Coq or standalone shell source was found in the runtime. The shell
entry is extracted from the plugin hook configuration; it is never launched.

The inventory covers explicit runtime functions, methods, lambdas, module
initialization, calls, shell entry, input/effect boundaries. It is NOT proof of
implicit Python operations, generated NamedTuple constructors, exceptions,
callback aliases or dynamic dispatch. Call edges are conservative source
bindings; unresolved dispatch is an EMPTY slot, not an asserted resolution.
Each explicit call has an invocation, argument/keyword and return edge.
Variadic expansion, defaults, mutation, control flow and argument expressions
need additional constraints. Return consumption is not yet a complete SSA
model. SLOTS and WIRES are reviewable inventory, not a zero verdict.

REQUIREMENTS uses the docs-def README as authority and records finite semantic
shape requirements. DOMAINS is initially empty. Missing and over are set
differences: accepted outside allowed, and required outside accepted. Unknown
domains are missing constraints. Declared domains additionally need a matching
source Literal type; arbitrary domain tables cannot prove implementation.
These finite tags do not yet encode the entire runtime behavioral contract.
Requirement coverage currently proves port existence only, not behavior.

Plant reports require a newly introduced diagnostic even when baseline already
fails. They are sensitivity tests, not claims of a passing baseline. Copies
exclude git and credential/config directories and are deleted afterward.
Receipt checks require observations and current plugin hashes; provenance is
operator evidence, not independently authenticated installation proof.
Whole-repo cleanliness requires actual clean git status, so the requested
uncommitted changes intentionally leave that bar unmet.

The seed condenses all wire edges into strongly connected components before
layering them. Argument/return feedback creates cycles; these cannot be treated
as independent tasks. Concurrency means graph independence only; write-scope
conflicts require remeasurement. It is a predicted route ending at zero,
not evidence zero is currently reachable with these unresolved contracts.
