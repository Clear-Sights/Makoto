"""The PostToolUse note naming the program to run, once per edited file until run (through hooks.json)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_lean2 as base  # noqa: E402


class Session(base.Session):
    def post(self, tool, tool_input, response):
        self.n += 1
        tid = 't%d' % self.n
        base.send(self.tmp, self.ev('PreToolUse', tool_name=tool, tool_use_id=tid, tool_input=tool_input))
        return base.send(self.tmp, self.ev('PostToolUse', tool_name=tool, tool_use_id=tid, tool_input=tool_input, tool_response=response))

    def put(self, path, text):
        (self.cwd / path).write_text(text, encoding='utf-8')
        return self.post('Write', {'file_path': path, 'content': text}, {'content': 'ok'})

    def exec(self, command):
        return self.post('Bash', {'command': command}, {'stdout': '1\n', 'exitCode': 0})


def note(response):
    out = response['hookSpecificOutput']
    assert out['hookEventName'] == 'PostToolUse' and 'decision' not in response
    return out['additionalContext']


def importer(tmp):
    s = Session(tmp)
    s.put('show.py', 'import app.mod\nprint(app.mod.f())\n')
    return s


def test_a_note_names_importer_and_edited_file(tmp_path):
    s = importer(tmp_path)
    assert note(s.put('app/mod.py', 'def f():\n    return 1\n')) == \
        'Before your final answer, run python3 show.py and read its output: it runs app/mod.py.'


def test_b_second_edit_before_a_run_has_no_note(tmp_path):
    s = importer(tmp_path)
    assert s.put('app/mod.py', 'def f():\n    return 1\n') != {}
    assert s.put('app/mod.py', 'def f():\n    return 2\n') == {}


def test_c_non_python_write_has_no_note(tmp_path):
    s = importer(tmp_path)
    assert s.put('app/notes.txt', 'hello\n') == {}


def test_d_edit_after_a_run_has_a_note_again(tmp_path):
    s = importer(tmp_path)
    s.put('app/mod.py', 'def f():\n    return 1\n')
    s.exec('python3 show.py')
    assert 'python3 show.py' in note(s.put('app/mod.py', 'def f():\n    return 2\n'))
