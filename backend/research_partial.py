"""Read complete JSON values from a truncated response; never invent closing data."""
import json


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON key')
        value[key] = item
    return value


DECODER = json.JSONDecoder(object_pairs_hook=unique_object)


def normalize_layout(raw):
    # Some providers emit literal escaped whitespace OUTSIDE JSON strings.
    # Preserve all characters inside strings, including evidence and escapes.
    out = []; quoted = False; escaped = False; i = 0
    while i < len(raw):
        char = raw[i]
        if not quoted and char == '\\' and raw[i:i+2] in ('\\n', '\\r', '\\t'):
            out.append(' '); i += 2; continue
        out.append(char)
        if quoted:
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        i += 1
    return ''.join(out)


def complete_prefix(raw):
    """Return preceding report metadata and whole findings before the broken tail."""
    if not isinstance(raw, str) or len(raw) > 500_000:
        raise ValueError('Invalid analysis response')
    raw = normalize_layout(raw.strip())
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    pos = 0; result = {}; findings = []
    def space(p):
        while p < len(raw) and raw[p].isspace(): p += 1
        return p
    if not raw.startswith('{'): raise ValueError('Invalid analysis response')
    pos = 1
    while True:
        pos = space(pos)
        key, pos = DECODER.raw_decode(raw, pos)
        if not isinstance(key, str) or key in result: raise ValueError('Invalid report key')
        pos = space(pos)
        if raw[pos:pos+1] != ':': raise ValueError('Invalid report separator')
        pos = space(pos+1)
        if key == 'findings':
            if raw[pos:pos+1] != '[': raise ValueError('Invalid findings')
            pos += 1
            while len(findings) < 20:
                try:
                    finding, end = DECODER.raw_decode(raw, space(pos))
                except json.JSONDecodeError: break
                if not isinstance(finding, dict): break
                findings.append(finding)
                pos = space(end)
                if raw[pos:pos+1] != ',': break
                pos += 1
            break
        value, pos = DECODER.raw_decode(raw, pos)
        result[key] = value
        pos = space(pos)
        if raw[pos:pos+1] != ',': raise ValueError('No complete findings')
        pos += 1
    if not findings or not all(k in result for k in ('title','firm','report_date','date_evidence')):
        raise ValueError('Incomplete report metadata or findings')
    # Optional trailing sections are not assumed to have been analyzed.
    return {k: result[k] for k in ('title','firm','report_date','date_evidence')} | {'findings': findings}
