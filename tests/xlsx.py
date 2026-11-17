#!/usr/bin/env python3
"""xlsx.py: read and write .xlsx workbooks with the standard library only.
  python3 xlsx.py --xlsx FILE    print each sheet as `## sheet` and its rows, tab-separated
  read_xlsx(path) -> [(sheet, [row, ...])]    write_xlsx(path, [(sheet, rows)])  same rows, same bytes
  filtered(path) -> {sheet: autoFilter ref}
Copied from Clear-Sights/hub-reborn check.py."""
import re
import sys
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RNS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def col(ref):
    n = 0
    for ch in re.match('[A-Z]+', ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


SIMPLE = re.compile(r'<c r="([A-Z]+)\d+" t="s"><v>(\d+)</v></c>')
ROW = re.compile(r'<row r="\d+">(.*?)</row>', re.S)


def fast(data, shared):
    """The rows of a sheet written by write_xlsx with shared strings, read by pattern; None for any other sheet."""
    rows = []
    for body in ROW.findall(data):
        found = SIMPLE.findall(body)
        if len(found) != body.count('<c '):
            return None
        cells = []
        for letters, n in found:
            i = col(letters)
            cells += [''] * (i - len(cells) + 1)
            cells[i] = shared[int(n)]
        rows.append(cells)
    return rows if data.count('<row ') == len(rows) else None


def read_xlsx(path, only=None):
    """[(sheet name, [row, ...])] in workbook order, from a .xlsx, standard library only; only the sheet `only` when it is given."""
    with zipfile.ZipFile(path) as z:
        def xml(n):
            return ET.fromstring(z.read(n))
        shared = [''.join(t.text or '' for t in si.iter(NS + 't')) for si in xml('xl/sharedStrings.xml')] \
            if 'xl/sharedStrings.xml' in z.namelist() else []
        targets = {r.get('Id'): r.get('Target') for r in xml('xl/_rels/workbook.xml.rels')}
        out = []
        for sh in xml('xl/workbook.xml').find(NS + 'sheets'):
            if only is not None and sh.get('name') != only:
                continue
            t = targets[sh.get(RNS + 'id')].lstrip('/')
            data = z.read(t if t.startswith('xl/') else 'xl/' + t).decode('utf-8')
            rows = fast(data, shared)
            if rows is not None:
                out.append((sh.get('name'), rows))
                continue
            rows = []
            for r in ET.fromstring(data).iter(NS + 'row'):
                cells = []
                for c in r.iter(NS + 'c'):
                    i = col(c.get('r'))
                    cells += [''] * (i - len(cells) + 1)
                    v = c.find(NS + 'v')
                    if c.get('t') == 's':
                        cells[i] = shared[int(v.text)]
                    elif c.get('t') == 'inlineStr':
                        cells[i] = ''.join(x.text or '' for x in c.iter(NS + 't'))
                    elif v is not None:
                        cells[i] = v.text or ''
                rows.append(cells)
            out.append((sh.get('name'), rows))
        return out


def write_xlsx(path, sheets, filters=True, compress=False):
    """Write [(name, rows)] as .xlsx: fixed timestamps, so the same rows give the same bytes; stored, or deflated for a large sheet."""
    def span(rows):
        j = len(rows[0]) - 1
        return 'A1:%s%d' % ((chr(64 + j // 26) if j >= 26 else '') + chr(65 + j % 26), len(rows))

    strings = {}

    def cell(j, n, v):
        if compress:   # a large sheet: each distinct text is kept once, in sharedStrings.xml
            return '<c r="%s%d" t="s"><v>%d</v></c>' % ((chr(64 + j // 26) if j >= 26 else '') + chr(65 + j % 26), n, strings.setdefault(v, len(strings)))
        return '<c r="%s%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % ((chr(64 + j // 26) if j >= 26 else '') + chr(65 + j % 26), n, escape(v))

    def sheet(rows):
        body = ''.join('<row r="%d">%s</row>' % (n, ''.join(cell(j, n, v) for j, v in enumerate(r))) for n, r in enumerate(rows, 1))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="%s"><sheetData>%s'
                '</sheetData>%s</worksheet>' % (NS[1:-1], body, '<autoFilter ref="%s"/>' % span(rows) if filters else ''))
    head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    r = 'http://schemas.openxmlformats.org/package/2006/relationships'
    o = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    files = [('[Content_Types].xml', head + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
              + ''.join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i
                        for i in range(1, len(sheets) + 1)) + '</Types>'),
             ('_rels/.rels', head + '<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s/officeDocument" Target="xl/workbook.xml"/></Relationships>' % (r, o)),
             ('xl/workbook.xml', head + '<workbook xmlns="%s" xmlns:r="%s"><sheets>%s</sheets>%s</workbook>' % (
                 NS[1:-1], o, ''.join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(n, {'"': '&quot;'}), i, i)
                                      for i, (n, _) in enumerate(sheets, 1)),
                 '<definedNames>%s</definedNames>' % ''.join(
                     '<definedName name="_xlnm._FilterDatabase" localSheetId="%d" hidden="1">\'%s\'!$A$1:$%s$%d</definedName>' % (
                         i, escape(n.replace("'", "''")), (lambda j: (chr(64 + j // 26) if j >= 26 else '') + chr(65 + j % 26))(len(rows[0]) - 1), len(rows)) for i, (n, rows) in enumerate(sheets)) if filters else '')),
             ('xl/_rels/workbook.xml.rels', head + '<Relationships xmlns="%s">%s</Relationships>' % (r, ''.join(
                 '<Relationship Id="rId%d" Type="%s/worksheet" Target="worksheets/sheet%d.xml"/>' % (i, o, i)
                 for i in range(1, len(sheets) + 1))))]
    files += [('xl/worksheets/sheet%d.xml' % i, sheet(rows)) for i, (_, rows) in enumerate(sheets, 1)]
    if strings:
        files.append(('xl/sharedStrings.xml', head + '<sst xmlns="%s" count="%d" uniqueCount="%d">%s</sst>' % (
            NS[1:-1], len(strings), len(strings), ''.join('<si><t xml:space="preserve">%s</t></si>' % escape(t) for t in strings))))
        files[0] = (files[0][0], files[0][1].replace('</Types>', '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>'))
        k = [i for i, f in enumerate(files) if f[0] == 'xl/_rels/workbook.xml.rels'][0]
        files[k] = (files[k][0], files[k][1].replace('</Relationships>', '<Relationship Id="rId%d" Type="%s/sharedStrings" Target="sharedStrings.xml"/></Relationships>' % (len(sheets) + 1, o)))
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED, compresslevel=9) as z:
        for name, data in files:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
            z.writestr(info, data, compresslevel=9)


def filtered(path):
    """{sheet name: autoFilter ref} of a .xlsx."""
    with zipfile.ZipFile(path) as z:
        names = [sh.get('name') for sh in ET.fromstring(z.read('xl/workbook.xml')).find(NS + 'sheets')]
        found = {}
        for i, n in enumerate(names, 1):
            f = ET.fromstring(z.read('xl/worksheets/sheet%d.xml' % i)).find(NS + 'autoFilter')
            if f is not None:
                found[n] = f.get('ref')
        return found


def show_xlsx(path):
    for name, rows in read_xlsx(path):
        print('## ' + name)
        for r in rows:
            print('\t'.join(c.replace('\t', ' ').replace('\n', '\\n') for c in r))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--xlsx':
        show_xlsx(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(2)
