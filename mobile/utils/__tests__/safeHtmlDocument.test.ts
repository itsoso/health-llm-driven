import { parseSafeHtmlDocument } from '../safeHtmlDocument';

const document = (body: string, head = '<title>合成阅读示例</title>') => '```html\n<!doctype html><html lang="zh-CN"><head>' + head + '</head><body>' + body + '</body></html>\n```';

describe('safe static HTML document', () => {
  it('renders complete fenced static text while ignoring style and metadata', () => {
    const source = document('<main><h1>合成计划</h1><p>第一段 &amp; 第二段<br>续行</p><ul><li>项目甲</li><li><strong>项目乙</strong></li></ul></main>', '<meta charset="utf-8"><style>body { color:red; background:url(https://invalid.example/a); }</style><title>标题</title>');
    const parsed = parseSafeHtmlDocument(source);
    expect(parsed?.blocks.map(block => block.text)).toEqual(['合成计划', '第一段 & 第二段\n续行', '项目甲', '项目乙']);
    expect(parsed?.blocks.map(block => block.kind)).toEqual(['heading', 'paragraph', 'list', 'list']);
  });
  it.each(['<script>alert(1)</script>', '<a href="https://example.com">链接</a>', '<img src="https://example.com/a">', '<form><input></form>', '<svg></svg>', '<p onclick="x()">文字</p>', '<table><tr><td colspan="2">合并</td></tr></table>', '<p>未闭合', '<unknown>文字</unknown>'])('retains unsupported document as source: %s', body => {
    expect(parseSafeHtmlDocument(document(body))).toBeNull();
  });
  it.each(['<meta http-equiv="refresh" content="0;url=https://example.com">', '<link rel="stylesheet" href="x">', '<script>x</script>'])('rejects active head markup', head => {
    expect(parseSafeHtmlDocument(document('<p>文字</p>', head))).toBeNull();
  });
  it('requires the full fenced document and never promotes nested code', () => {
    expect(parseSafeHtmlDocument('<html><head></head><body><p>正文</p></body></html>')).toBeNull();
    expect(parseSafeHtmlDocument(document('<p>正文</p>').slice(0, -3))).toBeNull();
    expect(parseSafeHtmlDocument('```text\n' + document('<p>正文</p>') + '\n```')).toBeNull();
    expect(parseSafeHtmlDocument('```html\n<body><p>正文</p></body>\n```')).toBeNull();
  });
  it('fails closed at source, depth, block and text limits without partial output', () => {
    for (const body of ['<p>' + '甲'.repeat(33000) + '</p>', '<div>'.repeat(25) + '甲' + '</div>'.repeat(25), '<p>甲</p>'.repeat(201), '<p>' + '甲'.repeat(4001) + '</p>', ('<p>' + '甲'.repeat(4000) + '</p>').repeat(5)]) {
      expect(parseSafeHtmlDocument(document(body))).toBeNull();
    }
  });
});

it('preserves ordered numbering, nesting and parent continuation', () => {
  const parsed = parseSafeHtmlDocument(document('<ol><li><p>第一项首段</p><p>第一项续段</p><ul><li>子项</li></ul><p>父项续文</p></li><li>第二项</li></ol>'));
  expect(parsed?.blocks).toEqual([
    { kind: 'list', text: '第一项首段', marker: '1.', depth: 0 },
    { kind: 'list', text: '第一项续段', marker: '', depth: 0 },
    { kind: 'list', text: '子项', marker: '•', depth: 1 },
    { kind: 'list', text: '父项续文', marker: '', depth: 0 },
    { kind: 'list', text: '第二项', marker: '2.', depth: 0 },
  ]);
});

it.each(['<ol start="3"><li>甲</li></ol>', '<ol reversed><li>甲</li></ol>', '<ol><li value="8">甲</li></ol>'])('rejects unsupported list numbering attributes', body => {
  expect(parseSafeHtmlDocument(document(body))).toBeNull();
});


it('retains empty parents and restarts nested ordered counters independently', () => {
  const blocks = parseSafeHtmlDocument(document('<ol><li><ol><li>子甲</li><li>子乙</li></ol></li><li></li><li>父丙</li></ol>'))?.blocks;
  expect(blocks?.map(({ text, marker, depth }) => [text, marker, depth])).toEqual([
    ['', '1.', 0], ['子甲', '1.', 1], ['子乙', '2.', 1], ['', '2.', 0], ['父丙', '3.', 0],
  ]);
});
