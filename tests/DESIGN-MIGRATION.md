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

## Reading and check refit

- `test_evidence::test_transcript_includes_earlier_turns_and_excludes_assistant`: D16.
- `test_evidence::test_host_current_turn_metadata_does_not_import_candidate_receipts`: D16.
- `test_names::test_own_file_contents_never_pay_unread_names`: D16.
- `test_shapes::test_b_only_assistant_text_never_pays`: D16.
- `test_shapes::test_agnostic_tool_response_and_prior_input`: D16.
- `test_shapes::test_git_syntax_is_a_boundary`: D16.
- `test_shapes::test_candidate_content_and_tool_metadata_do_not_pay_themselves`: D16.
- `test_no_findings::test_findings_alone_hold`: D16.
- `test_evidence::test_transcript_prior_write_invalidates_old_read`: D17.
- `test_shapes::test_c_external_subject_needs_current_online_call`: D16.
- `test_shapes::test_staleness_after_any_write_and_own_readback`: D17.
- `test_shapes::test_invalid_receipts_cannot_pay`: D17 (historical literal origin remains; replay still supplies no new reading).
- `test_shapes::test_old_read_is_eligible_until_subject_written`: D17.
- `test_windows_paths::test_cross_drive_edit_and_writer_reference_need_no_relpath`: D18.
- `test_built_pairs::test_built_pair (and installed/orthogonal consumers)`: D16/D17/D18: doubles use a numeric value to isolate a; stale twins claim the changed path; switch twins assert behavior.
- `test_switch::test_unrun_code_holds_each_dependent_boundary`: D18: writer claims assert behavior.
- `test_switch::test_writer_references_path_module_or_declared_identifier`: D18: behavior selects; recorded values do not.
- `test_switch::test_package_module_name_and_run_resolve_the_same_recorded_path`: D18: assert behavior.
- `test_switch::test_compact_json_key_is_a_named_edited_identifier`: D18: assert behavior.
- `test_other_point::test_url_host_is_a_point_even_after_online_search`: D16 requires fetching the claimed URL or returning it in search; fetching a different host also leaves b.
