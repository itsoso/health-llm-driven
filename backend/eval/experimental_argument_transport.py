"""Unapproved transport experiment; never imported by application runtime."""
import json


def _compact(value):
    if not isinstance(value, str) or not value.lstrip().startswith(('{', '[')):
        return value
    def reject_constant(value):
        raise ValueError('non_json_constant')
    try:
        json.loads(value, parse_int=str, parse_float=str, parse_constant=reject_constant)
    except (ValueError, RecursionError):
        return value
    output = []
    quoted = escaped = False
    for char in value:
        if quoted:
            output.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            output.append(char)
            quoted = True
        elif char not in ' \t\r\n':
            output.append(char)
    return ''.join(output)


def compact_call_arguments(messages):
    result = []
    for message in messages:
        calls = message.get('tool_calls')
        if message.get('role') != 'assistant' or not isinstance(calls, list):
            result.append(message)
            continue
        projected = []
        for call in calls:
            function = call.get('function') if isinstance(call, dict) else None
            if not isinstance(function, dict) or call.get('type') != 'function':
                projected.append(call)
                continue
            arguments = function.get('arguments')
            compacted = _compact(arguments)
            projected.append({**call, 'function': {**function, 'arguments': compacted}}
                             if compacted != arguments else call)
        result.append({**message, 'tool_calls': projected})
    return result
