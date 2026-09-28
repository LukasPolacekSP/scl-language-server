"""Tests for the current parser_structured.py implementation directly.

Unlike test_diagnostics.py / test_handlers.py, these tests DO look at the
parser's internal shape (VariableNode, `.variables`, `.all_nodes`) rather
than only at LSP-facing output. That's intentional: this file exists to
pin down today's regex/line-based parser while it still exists.

If/when the parser is rewritten (e.g. as a trie/word-tree, or in another
language entirely), this file is the one expected to need rewriting or
replacing - test_diagnostics.py and test_handlers.py should keep passing
unchanged as long as the observable LSP behavior doesn't regress.
"""
from parser_structured import StructuredSCLParser, get_parser, update_parser


def test_get_parser_returns_a_singleton():
    a = get_parser()
    b = get_parser()
    assert a is b


def test_var_input_output_and_static_blocks_are_classified():
    parser = StructuredSCLParser()
    parser.parse(
        """
        FUNCTION_BLOCK FB_Example
        VAR_INPUT
            bStart : BOOL;
        END_VAR
        VAR_OUTPUT
            bRunning : BOOL;
        END_VAR
        VAR
            iCounter : INT := 0;
        END_VAR
        BEGIN
        END_FUNCTION_BLOCK
        """
    )

    assert parser.variables["bStart"].var_type == "input"
    assert parser.variables["bRunning"].var_type == "output"
    assert parser.variables["iCounter"].var_type == "static"
    assert parser.variables["iCounter"].default == "0"


def test_constant_definition_is_captured():
    parser = StructuredSCLParser()
    parser.parse(
        """
        CONST
            MAX_SPEED := INT#100;
        END_CONST
        BEGIN
        END_FUNCTION_BLOCK
        """
    )

    node = parser.variables["MAX_SPEED"]
    assert node.var_type == "constant"
    assert node.data_type == "INT"
    assert node.default == "100"


def test_nested_struct_fields_get_dotted_paths():
    parser = StructuredSCLParser()
    parser.parse(
        """
        VAR
            Motor : STRUCT
                Status : STRUCT
                    bRunning : BOOL; // running flag
                END_STRUCT;
                iSpeed : INT := 100;
            END_STRUCT;
        END_VAR
        BEGIN
        END_FUNCTION_BLOCK
        """
    )

    assert "Motor" in parser.variables
    assert parser.variables["Motor"].data_type == "STRUCT"

    assert "Motor.Status" in parser.all_nodes
    assert "Motor.Status.bRunning" in parser.all_nodes
    assert "Motor.iSpeed" in parser.all_nodes

    running_node = parser.all_nodes["Motor.Status.bRunning"]
    assert running_node.data_type == "BOOL"
    assert running_node.comment == "running flag"

    speed_node = parser.all_nodes["Motor.iSpeed"]
    assert speed_node.default == "100"

    # Children are reachable from their parent, matching how handlers.py
    # walks the tree for completion.
    assert "Status" in parser.variables["Motor"].children
    assert "bRunning" in parser.variables["Motor"].children["Status"].children


def test_function_block_call_arguments_are_tracked_as_children():
    parser = StructuredSCLParser()
    parser.parse(
        """
        VAR
            bStart : BOOL;
            iSpeed : INT;
        END_VAR
        BEGIN
        MyMotor(
            Start := bStart,
            Speed := iSpeed
        );
        END_FUNCTION_BLOCK
        """
    )

    call_node = parser.all_nodes["MyMotor"]
    assert call_node.var_type == "function_block_call"
    assert set(call_node.children.keys()) == {"Start", "Speed"}
    assert all(child.var_type == "fb_argument" for child in call_node.children.values())


def test_update_parser_reparses_from_the_document_source():
    doc_v1 = _StubDoc("VAR\n    iValue : INT;\nEND_VAR\nBEGIN\nEND_FUNCTION_BLOCK\n")
    update_parser(doc_v1)
    parser = get_parser()
    assert "iValue" in parser.variables

    doc_v2 = _StubDoc("VAR\n    sName : STRING;\nEND_VAR\nBEGIN\nEND_FUNCTION_BLOCK\n")
    update_parser(doc_v2)
    parser_after = get_parser()

    # Same singleton instance, but its state reflects only the latest parse.
    assert parser_after is parser
    assert "sName" in parser_after.variables
    assert "iValue" not in parser_after.variables


class _StubDoc:
    def __init__(self, source: str):
        self.source = source
