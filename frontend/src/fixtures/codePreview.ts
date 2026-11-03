// Synthetic demonstration code.
// This is not source retrieved from the registered repository.

export const codePreview = {
  filePath: 'fixtures/demo_resolver.py',
  language: 'python',
  startLine: 1,
  highlightStart: 4,
  highlightEnd: 9,
  code: [
    'class DemoResolver:',
    '    """Synthetic example for testing the code viewer."""',
    '',
    '    def resolve_calls(self, names, symbol_table):',
    '        resolved = []',
    '        for name in names:',
    '            if name in symbol_table:',
    '                resolved.append(symbol_table[name])',
    '        return resolved',
  ].join('\n'),
};