class Indexer:
    def index(self, source: str) -> list[str]:
        return parse(source)


def parse(source: str) -> list[str]:
    return source.splitlines()