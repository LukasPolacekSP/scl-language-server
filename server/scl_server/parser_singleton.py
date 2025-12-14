"""Shared parser singleton to ensure all modules use the same parser instance."""

from parser_structured import StructuredSCLParser

# Single shared parser instance
_parser_instance = None

def get_parser():
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = StructuredSCLParser()
    return _parser_instance

def update_parser(doc):
    parser = get_parser()
    parser.parse(doc.source)
