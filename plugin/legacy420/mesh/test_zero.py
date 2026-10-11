"""Completion must execute acceptance even in the presence of forged receipts."""
import json
from pathlib import Path
import tempfile
import unittest

from zero import derive_waves, implementation


class CompletionTests(unittest.TestCase):
    def test_receipt_cannot_override_product_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'tests').mkdir()
            (root/'mesh/evidence').mkdir(parents=True)
            receipt = root/'mesh/evidence/join.json'
            receipt.write_text(json.dumps({'task': 'join', 'result': 'pass',
                                           'done': True, 'decision': 'done'}))
            product = root/'tests/acceptance_tasks.py'
            product.write_text('def test_join():\n    assert 1 + 1 == 2\n'
                               'def test_subtract():\n    assert True\n')
            slots = [{'slot': 'join'}]
            self.assertEqual(implementation(root, slots)[1:], ([], []))
            product.write_text('def test_join():\n    assert 1 + 1 == 3\n'
                               'def test_subtract():\n    assert True\n')
            states, absent, external = implementation(root, slots)
            self.assertFalse(states['join']['accepted'])
            self.assertEqual(absent, ['join:product_acceptance'])
            self.assertEqual(external, [])
            self.assertEqual(json.loads(receipt.read_text())['result'], 'pass')
            product.unlink()
            self.assertIn('join:product_acceptance', implementation(root, slots)[1])

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
