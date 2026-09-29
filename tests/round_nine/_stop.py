"""Shared shape for round nine's Stop-gate plants: the file is on disk under the case cwd AND
written by a settled Write, then the turn stops. Underscore-prefixed: the runner skips it."""


def written(row, name, path, content, others=None):
    """A case whose one act is a Write of `content` to `path` (relative to the case cwd);
    `others` are files already on disk that the turn did not write."""
    return dict(name=name, row=row, files=dict(others or {}, **{path: content}),
                events=[{"hook_event_name": "PostToolUse", "tool_name": "Write",
                         "tool_input": {"file_path": "{cwd}/" + path, "content": content},
                         "tool_response": {}},
                        {"hook_event_name": "Stop", "last_assistant_message": ""}])
