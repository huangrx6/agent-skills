"""Parse HTML attributes without assuming a particular quoting style."""
from html.parser import HTMLParser


class Tags(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.offsets = [0]
        for line in source.splitlines(keepends=True):
            self.offsets.append(self.offsets[-1] + len(line))
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        line, column = self.getpos()
        raw = self.get_starttag_text()
        self.tags.append((tag, attrs, raw, self.offsets[line - 1] + column))

    handle_startendtag = handle_starttag
