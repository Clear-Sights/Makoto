# 0017: Table-driven event routing

Date: 2026-08-16

## Relocated design history

From the `HANDLERS` mapping:

```text
# The table: hook_event_name -> the event's pipeline. This is the whole routing — adding an
# event is adding one row plus (at most) one handler above, never another branch in main()
# (the same "a capability is a row, never a module" discipline as Detent's MOVES). The
# lookup's default is _evaluate_and_gate, the wildcard law: an event with no specialist row
# is held to the predicate catalog, so a newly wired event can never silently bypass
# evaluation — exactly the fall-through main()'s old if/elif chain provided, now as data.
```
