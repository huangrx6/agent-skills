"""Read draw.io XML, including pages saved with the editor's raw-deflate codec."""
import base64
import binascii
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

MAX_PAGE_BYTES = 16 * 1024 * 1024


def xml(text):
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('不接受 XML 文档类型或实体声明')
    return ET.fromstring(text)


def parse(text):
    root = xml(text)
    if root.tag != 'mxfile':
        raise ValueError('需要 <mxfile> draw.io 文件')
    for page in root.findall('diagram'):
        if page.find('mxGraphModel') is not None:
            continue
        payload = (page.text or '').strip()
        if not payload:
            raise ValueError('空的 draw.io 页，没有 <mxGraphModel>')
        try:
            if payload.startswith('<'):
                decoded = payload  # XML escaped by the containing document
            else:
                if len(payload) > MAX_PAGE_BYTES * 2:
                    raise ValueError('压缩页超过大小上限')
                data = base64.b64decode(''.join(payload.split()), validate=True)
                inflater = zlib.decompressobj(-15)
                raw = inflater.decompress(data, MAX_PAGE_BYTES + 1)
                if len(raw) > MAX_PAGE_BYTES or inflater.unconsumed_tail:
                    raise ValueError('解压页超过 16 MiB 上限')
                if not inflater.eof or inflater.unused_data:
                    raise ValueError('不完整或多余的压缩数据')
                decoded = urllib.parse.unquote(raw.decode('utf-8'), errors='strict')
            model = xml(decoded)
            if model.tag != 'mxGraphModel':
                raise ValueError('解压后不是 <mxGraphModel>')
        except (binascii.Error, zlib.error, UnicodeError, ET.ParseError, ValueError) as exc:
            raise ValueError(f'页 {page.get("name", "?")} 的压缩/XML 内容无效：{exc}') from exc
        page.text = None
        page.append(model)
    return root
