"""Completion controls; no runtime, external files or operator actions."""
import copy
import unittest

from zero import canonical, derive_waves, implementation, receipt_state, sha


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.files = {'mesh/input': b'current'}
        pins = {n: sha(b) for n, b in self.files.items()}
        self.receipt = dict(source_pins=pins, selected_input_digest=sha(canonical(pins)),
                            result='pass', observations=[dict(result='pass', synthetic=False)])

    def test_current_and_changed_inputs(self):
        self.assertTrue(receipt_state(self.receipt, self.files)['accepted'])
        for files in ({}, {'mesh/input': b'changed'}):
            self.assertFalse(receipt_state(self.receipt, files)['accepted'])

    def test_invalid_or_missing_selection(self):
        for change in (dict(source_pins={}), dict(selected_input_digest='0'*64),
                       dict(source_pins={'mesh/input': 'z'*64})):
            self.assertFalse(receipt_state(dict(self.receipt, **change), self.files)['accepted'])

    def test_outside_evidence_is_external(self):
        pins = {'runtime.py': sha(b'current')}
        receipt = dict(self.receipt, source_pins=pins, selected_input_digest=sha(canonical(pins)))
        state = receipt_state(receipt, {'runtime.py': b'current'})
        self.assertFalse(state['accepted'])
        self.assertEqual(state['outside_evidence'], ['runtime.py'])

    def test_passing_label_cannot_hide_absence(self):
        for change in (dict(absent=['approval']), dict(external=['operator']),
                       dict(status='EXTERNAL'), dict(done=False), dict(decision='not_done'),
                       dict(observations=[dict(result='pass', synthetic=True)]),
                       dict(observations=[dict(result='fail')])):
            self.assertFalse(receipt_state(dict(self.receipt, **change), self.files)['accepted'])

    def test_all_current_evidence_required(self):
        slots = [dict(slot=n, requirements=n, **{'fill-status': 'CANDIDATE', 'filled-by': 'mesh/proof.py:proof'})
                 for n in ('join', 'handoff')]
        receipts = {n: dict(self.receipt, task=n, requirements=[n]) for n in ('join', 'handoff')}
        receipts['join'].update(decision='done', verdict=dict(decision='done'))
        self.assertEqual(implementation(receipts, self.files, slots)[1:], ([], []))
        for n in receipts:
            changed = copy.deepcopy(receipts)
            changed[n]['selected_input_digest'] = '0'*64
            self.assertTrue(implementation(changed, self.files, slots)[1])
        slots[0]['fill-status'] = 'OPEN'
        self.assertIn('join:bound_proof_producer', implementation(receipts, self.files, slots)[1])

    def test_waves_rederive_on_changed_dependencies(self):
        tasks = [dict(task='a', deps='', estimate_tokens='1'),
                 dict(task='b', deps='', estimate_tokens='2')]
        self.assertEqual(derive_waves(tasks)[0]['tasks'], ['a', 'b'])
        tasks[1]['deps'] = 'a'
        self.assertEqual([w['tasks'] for w in derive_waves(tasks)], [['a'], ['b']])
        tasks[0]['deps'] = 'b'
        with self.assertRaises(ValueError):
            derive_waves(tasks)


if __name__ == '__main__':
    unittest.main()
