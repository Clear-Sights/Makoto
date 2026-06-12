"""pattern 1.1 predicate — verifier predicate weakened (loose-comparator shape).

Reads tool_input.content (NOT disk) per the §5.6 semantic-frame correction.
Scaffold extracted to lib.factories.regex_file_predicate (1.0.3 R1).
Knight-Leveson: stdlib re only.
"""
from __future__ import annotations
import re
from makoto.lib.factories import regex_file_predicate


predicate = regex_file_predicate(
    target_rx=re.compile(r"constitution/integrity/checks/[^/]+\.py$"),
    body_rx=re.compile(r"\bstartswith\(|\bendswith\(|\bre\.match\b|\bre\.search\b|\bin\s*\["),
)
