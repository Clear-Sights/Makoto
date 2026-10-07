# Existing regression expectations and DESIGN.md

Test function identities are retained for continuity with the prior suite.
Some historical names still refer to the former rule assignment. No test is
skipped or marked as an expected failure.

| Previous expectation | Replacement required by DESIGN.md | Retained/added discriminator |
|---|---|---|
| Any original reading clears lineage | D15 requires the asserted literal's origin | Unrelated originals do not clear it; an exact source response does |
| Unread literal is rule b | D15 owns literal origin; D16 owns reading the thing | A carrier mentioning a path clears a but leaves b; reading the path clears b |
| Typed arguments and pending input supply evidence | D4 requires returned source bytes | Pending input remains held until its matched result |
| Every step needs an artifact | D8 exempts assertion-free steps and creations | Transport tests now use an explicit literal claim; creation tests need no receipt |
| User-given literal still needs an unrelated artifact | D4 accepts user source statements, following CAUSES | User literals clear a; a user-given URL still lacks the thing reading for b |
| Own file names are always exempt | D4 permits a readback to establish its own file identity only | Writer acknowledgments do not clear a/b; readback clears the path, never copied own bytes |
| Stale literal is an unread name | D17 owns freshness independently of historical origin | Mutation changes a paid literal to c only |
| External classification/new turn alone requires online access | D17 requires an actual other-point/change condition | Missing page reading is b; an unchanged source stays usable; actual host/copy/mutation differences still hold c |
| Equal basenames prove a copy | D5 requires an identified subject/copy relation | Copy plants now record host aliases; unrelated equal basenames do not establish identity |
| Configuration readback clears execution | D11/D18 require an input and returned response | Readback leaves d; running the config consumer clears d |
| Commit test helper ignores its supplied text | D1 includes the actual commit message | The helper now carries that text; shipping tests explicitly use a message with no path |

The built pair collection independently exercises the new definitions at all
four planned boundaries. Every fault asserts the exact singleton rule set;
every clean twin supplies one source reading or one run. Orthogonality tests
reuse the entire collection with each decision function disabled separately.
