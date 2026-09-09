=========================================
THE BLINDSPOT REGISTER
=========================================
Find the family. Read down. Stop at the
one that stings.

A  the value isn't what you think
B  the check didn't check
C  the verdict didn't survive the trip
D  the effect didn't land
E  the right branch didn't run
F  true once, or true elsewhere
G  wrong question


===== A - THE VALUE ====================
A1  ABSENCE-AS-VALUE
    missing data defaults to a valid value
  > use a sentinel outside the valid range
A2  SURFACE-FORM IDENTITY
    same spelling taken as same thing
  > canonicalize; test both directions
A3  POSITIONAL PAIRING
    two sequences assumed to line up
  > join on a shared key
A4  LAST-WINS  (+A10)
    duplicate keys; which one wins is unstated
  > define the winner; test both orders
A5  WRAPPER STRIPPED
    the context around the value was dropped
  > compare whole output, not the inner value
A6  GRADIENT COLLAPSE
    a threshold maps near-perfect to zero
  > assert output tracks input throughout
A7  ONE-NUMBER CONFLATION  (+B27)
    one total hides parts that differ
  > compare per unit, at the grain you cite
A11 REPLAY COUNTED AS NEW
    a re-emission counted as a fresh occurrence
  > count distinct content, not records
A13 SETTING CALLED INHERENT
    a configured value described as a property
  > name which layer set it, and where it changes


===== B - THE CHECK ====================
B1  CHECKER SELF-TRUST  (+B3 B29)
    I wrote both the task and the oracle
  > see the verdict flip on a plant first
B2  VACUOUS GREEN  (+A9 B13)
    the assertion held over a set never counted
  > count the population independently, then the property
B4  WRONG ORACLE  (+B30)
    a stand-in graded some or all, not the target
  > find where proxy and target disagree
B5  MEASUREMENT THEATER
    the metric is a constant, not a measure
  > check where each metric is written
B6  DENOMINATOR DRIFT
    the total reported isn't the total graded
  > make counts sum, and name their run
B7  RULE WITH NO RUNNER  (+B15 B33 F11)
    written or cited, enforced nowhere live
  > bind every rule to a check on every path
B8  UNSEEN READ AS UNNEEDED  (+B22)
    absence taken as proof
  > prove it can't occur, or pair with a known-present case
B9  WAIVER NEVER EXPIRES  (+B25)
    an exemption with no checkable end
  > every waiver names a checkable discharge
B10 NEVER-ABSTAINING CHECK
    fires on everything, so says nothing
  > measure its rate on benign input
B11 BASELINE UNTAKEN  (+B12)
    a failure attributed without a graded base
  > run the baseline; grade it on its own bar
B14 MECHANISM AS OUTCOME
    built and firing, never shown to help
  > measure with and without
B17 PLANT CONTAMINATES DETECTOR
    the checker contains the pattern it hunts
  > require green before the plant
B18 IN-SAMPLE SELECTION  (+B19)
    scored only on what it was built from
  > report on something you didn't build
B20 PLANT WITHDRAWN
    the test input was edited until it passed
  > red-to-green must touch the subject
B21 OVERDETERMINED VERDICT
    a sibling condition gave the same answer
  > isolate each condition with its own input
B23 BOUND AS COUNT
    a ceiling with slack only says yes
  > assert equality; retighten on each change
B24 CITATION SCOPE CREEP
    real evidence attached to a bigger claim
  > check the source entails the sentence
B26 UNSUPERVISED SUPERVISOR
    the guarantor of delivery died unnoticed
  > make its liveness an output; absence fails loud
B28 ISOLATED CASES ONLY
    each case tested fresh; real runs are sequences
  > replay the real succession into shared state
B32 CLAIM RESTATES ITSELF
    the claim unfolds to itself; the proof is identity
  > reject a result whose proof does no work
B34 LAW EXEMPTS ITS INSTRUMENT
    the law it enforces, its own machinery breaks
  > run the artifact's own law over the artifact;
    name every region it cannot


===== C - THE VERDICT ==================
C1  STATUS LOST IN TRANSIT
    the failure was computed, then dropped
  > plant one; watch the caller's status
C2  MISSING THIRD STATE
    "couldn't run" forced into pass or fail
  > carry not-evaluable in its own field
C3  MASK
    one item's signal hides the rest
  > evaluate each item in isolation
C4  CRASH PERMITS
    the checker failed, so the act proceeded
  > an error resolves as a denial
C5  FALLTHROUGH  (+B16 E2)
    no branch for the shape that arrived
  > every dispatch ends in an error; feed foreign shapes
C6  SIGN INVERTED
    right number, wrong direction recorded
  > state the wanted direction beforehand
C7  TRUNCATION AS COMPLETION
    an interrupted producer's partial output accepted
  > require a terminator or a count
C8  LAUNCHER EXIT AS JOB EXIT
    the starter returned; the work still ran
  > wait on something the work itself emits
C9  DECISION ONLY IN THE WINDOW
    concluded, stated, never persisted
  > persist every gating decision
C10 ABSENCE ON ONE ROUTE
    the answer arrived by a route you never read
  > name every route; absence needs all of them


===== D - THE EFFECT ===================
D1  WRITE UNVERIFIED  (+A8 D5)
    a write or setting taken as its effect
  > read back through the consumer before trusting or retrying
D2  WRONG SCOPE  (+F5)
    right operation; landed where nothing consumes it
  > get evidence from the consumer's side
D3  SUBJECT UNPINNED  (+D7)
    the name or copy isn't the one graded
  > pin an immutable identity; re-resolve at use
D4  DERIVED ARTIFACT STALE  (+D6)
    a derivative older than its source
  > key on content; regenerate and compare
D8  SCALE UNTESTED  (+A12)
    proven small, or in another form
  > exercise at real magnitude, in the shipped form
D9  SELF-INCLUSION  (+D10)
    the actor or rule is inside its own set
  > exclude self by identity; plant a real instance
D11 REWRITE BY ROUNDTRIP
    the edit drowned in a whole-artifact rewrite
  > bound the change, or append
D12 PRESERVE TO VOLATILE
    the copy shares the fate it should survive
  > re-read it after the boundary
D13 UNENUMERATED DESTRUCTION
    removing a set you never listed
  > list first; act on exactly that list
D14 UNDO UNPROVEN
    a trial's residue could not be removed
  > prove the undo on that target first


===== E - THE BRANCH ===================
E1  SHADOWED BRANCH
    a case that can never be selected
  > every branch needs a witness input
E3  COINCIDENCE
    a pattern that matched by accident
  > require an explicit intent marker
E4  INHERITED DEFAULT
    the platform chose your posture
  > state every consequential setting yourself
E5  UNBOUNDED RETRY
    a loop whose only exit is success
  > cap it, with a path for "still failing"
E7  UNDECLARED ENVIRONMENT  (+E6)
    it runs only here; ambient state stood in for conditions
  > set every condition; run from clean
E8  OPTION INTERACTION
    each setting valid, the combination not
  > bisect, then pin the combination
E9  RECOVERY UNDEFINED HERE
    the fallback can't cover its own trigger
  > exercise it from the real failure state
E10 RETRY BLIND TO CLASS  (+F13)
    retrying without classifying the failure
  > map each class to retry or stop; name what changed
E11 NESTED BUDGET SHADOWED
    an outer limit smaller than yours
  > name the limiting layer before retrying
E12 PRINCIPAL EXCLUDED
    rewording can't grant what you can't hold
  > read which attribute the gate inspects
E13 PARKED ON AN INHERITED CHANNEL
    a detached task waits on input nobody sends
  > close or redirect every channel you don't feed


===== F - ELSEWHERE ====================
F1  SIBLING GAP
    the fix landed on one twin
  > enumerate every sibling and copy
F2  TWO SOURCES OF TRUTH
    one rule implemented twice, diverging
  > one owner; every consumer calls it
F3  STALE INVARIANT  (+F15)
    the referent moved since it was named
  > qualify it; re-resolve at use; assert it resolves
F4  SOURCE NEVER READ
    built against a description, not the thing
  > re-derive from the primary artifact
F6  MONOTONICITY ASSUMED
    removal resurrects, addition suppresses
  > walk the small state space
F7  CHECK-THEN-ACT RACE
    it moved between the check and the act
  > re-verify within the same exclusion
F8  STALE REFIRE
    the same alert forever, unread
  > suppress while unchanged; resurface on cadence
F10 DIGEST KEPT, SOURCE GONE  (+F9)
    trusting your own record of the event
  > re-derive or re-run it, or label it unverified
F12 CAUSE FROM SYMPTOM
    the first plausible mechanism became it
  > verify one discriminating observation
F14 DECLARED CLASS TRUSTED
    "no behavior change" that changed behavior
  > compare behavior, not text
F16 RECORD TRAILS LIVE STATE
    the record lags; newest items read as absent
  > check the record's watermark against now


===== G - WRONG QUESTION ===============
G1  GOAL SUBSTITUTION
    you answered a nearby, easier question
  > set the request beside the result
G2  DETERMINED ASKED AS OPEN  (+G4)
    a settled quantity or decision sent out as open
  > derive it; ask only what survives derivation
G3  SCOPE BELOW THE ANSWER
    each part sees less than the answer spans
  > give one party the whole span
G5  WALL WITHOUT INVENTORY
    "cannot" declared with the means already held
  > list what you hold before saying no


===== ADDING TO THIS REGISTER ==========
Add only what cost you something in this
run, with the incident in hand.

1  Write the fix line first, before the
   name. The fix is the entry's identity.

2  Set that fix beside every existing fix
   line, all families. If any one, applied,
   would have caught the incident, stop:
   cite that id. Two symptoms with one test
   are one entry. Widen the old wording if
   it needs to; never add a twin.

3  Strike every noun that names a tool,
   format, language, artifact, medium, or
   vendor. If the entry still reads, keep
   the struck version. If it doesn't, the
   entry was about the tool: rewrite until
   it does, or drop it.

4  Name one input that would trip this
   entry and no other. None: it's a twin.

5  Two fixes means two entries.

===== MERGING ==========================
A merge is a claim that one fix catches
both incidents. Prove it, both ways:

1  Name an input that trips the dropped
   entry. Apply the survivor's fix alone.
   If it doesn't catch that input, no merge.

2  Pick the survivor by fix, not by family
   or name. Same fix in another family is
   still the survivor.

3  Widen the survivor until step 1 passes
   for every id it carries. Then re-run
   step 1 for each of them: widening for
   one can loosen another.

4  Write the absorbed ids on the survivor:
   NAME  (+B15 B33 F11). Any later edit to
   that entry re-runs step 1 for each id
   listed. A gap in numbering with no
   carrier is an error.

Form: id, name, defect under ten words,
then "> " and the fix under ten.
Append within the family; never renumber,
entries cite these numbers.
