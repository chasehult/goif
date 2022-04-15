from enum import Enum, auto

from pyparsing import Char, Combine, Empty, Group, Keyword as _Keyword, LineEnd, Literal, OpAssoc, Opt, ParseResults, \
    ParserElement, Regex, SkipTo, StringEnd, Suppress, White, Word, alphanums, alphas, common, delimited_list, \
    infix_notation, \
    nums, one_of

from operator_exprs import operate

__author__ = "Chase Hult"


def Keyword(kw):
    return Suppress(_Keyword(kw, caseless=True))


ParserElement.set_default_whitespace_chars(' \t')  # Newlines have meaning in this grammar
ParserElement.enable_packrat()  # Enable memoization to speed up expression parsing

KEYWORDS = [
    "INTO", "GO", "GOIF", "JUMP", "THROW", "RETURN", "HANDLE", "LOAD",
    "TRUE", "FALSE",
]


def not_keyword(tokens):
    var, = tokens
    return var.strip() not in KEYWORDS


class SpecialValues(Enum):
    Empty = auto()


cfg_ws = Suppress(White())

cfg_var = common.identifier
cfg_var.add_condition(not_keyword)
cfg_expr_var = cfg_var.copy()
cfg_unset_var = Combine(Suppress('@') + Char(alphas + '_') + Char(alphanums + '_')[...])

cfg_empty = Literal("@").add_parse_action(lambda pr: SpecialValues.Empty)
cfg_int = common.signed_integer
cfg_str = Combine('"' + Word(nums) + '"')
# This is true because of special string handling.  We need to add our parse action later.
cfg_bool = Literal("TRUE") | Literal("FALSE")
cfg_bool.add_parse_action(lambda pr: pr[0] == 'TRUE')


def fold_expr(num=2):
    def _fold(expr):
        if len(expr) == 1:
            return expr[0]
        elif num == 1:
            op, a1 = expr
            return operate(op, a1)
        elif num == 2:
            # Dyadic operators with equal presidence chain in PyParsing
            #  so we need to do this recursively.
            # ex. 1+2+3 -> [1, +, 2, +, 3] rather than [[1, +, 2], +, 3]
            a1, op, *a2 = expr
            return operate(op, a1, _fold(a2))
        elif num == 3:
            a1, op, a2, _, a3 = expr
            return operate(op, a1, a2, a3)

    return lambda m: [_fold(m[0])]


cfg_expr = infix_notation(
    cfg_int | cfg_str | cfg_bool | cfg_expr_var | cfg_unset_var,
    [
        (one_of('-'), 1, OpAssoc.RIGHT, fold_expr(1)),
        (one_of('* / \\'), 2, OpAssoc.LEFT, fold_expr(2)),
        (one_of('+ -'), 2, OpAssoc.LEFT, fold_expr(2)),
        (one_of('#'), 2, OpAssoc.LEFT, fold_expr(2)),
        (one_of('^'), 2, OpAssoc.LEFT, fold_expr(2)),
        (one_of('!'), 1, OpAssoc.RIGHT, fold_expr(1)),
        (one_of('< <= == != >= >'), 2, OpAssoc.LEFT, fold_expr(2)),
        (one_of('& |'), 2, OpAssoc.LEFT, fold_expr(2)),
        (('?', ':'), 3, OpAssoc.RIGHT, fold_expr(3)),
    ]
)

cfg_exprs = Group((Suppress("(") + delimited_list(cfg_expr, delim=Suppress(",")) + Suppress(")")) | Empty())

cfg_abs_ln = Combine('^' + Opt('-') + Word(nums))
cfg_rel_ln = Combine('~' + Opt('-') + Word(nums))
cfg_lbl_ln = Word(alphanums + '._')
cfg_line_no = cfg_abs_ln | cfg_rel_ln | cfg_lbl_ln

cfg_file_id = Word(alphanums + '._')
cfg_line_id = Group(Opt(cfg_file_id + Suppress(":")).set_parse_action(lambda pr: pr or [None]) + cfg_line_no)

cfg_exception = Word(alphanums + '_')

cfg_handle_sbstmt = Keyword("HANDLE") + cfg_exception + cfg_ws + cfg_line_id

cfg_goif_file = Word(alphanums + '_./')

cfg_label_stmt = Combine(cfg_lbl_ln + ':')
cfg_load_file_id = cfg_file_id.copy().add_condition(lambda pr: pr[0].upper() != "MAIN")
cfg_load_stmt = Keyword("LOAD") + cfg_goif_file + cfg_ws + cfg_load_file_id
cfg_go_stmt = Keyword("GO") + cfg_line_id
cfg_goif_stmt = Keyword("GOIF") + cfg_line_id + cfg_ws + cfg_expr
cfg_jump_stmt = Keyword("JUMP") + cfg_line_id + cfg_exprs + Group(cfg_handle_sbstmt)[...]
cfg_throw_stmt = Keyword("THROW") + cfg_exception
cfg_ret_stmt = Keyword("RETURN") + cfg_exprs
cfg_into_stmt = (cfg_expr | cfg_empty) + cfg_ws + Keyword("INTO") + cfg_var

cfg_comment = Suppress(Literal("%") + Regex('[^\n]*'))

# Evaluation (Inert)
cfg_var_eval = Combine(Char(alphas + '_') + Char(alphanums + '_')[...])
cfg_var_eval.add_condition(not_keyword)
cfg_unset_var_eval = Combine(Suppress('@') + cfg_var_eval)

cfg_int_eval = common.signed_integer
cfg_str_eval = Combine(Literal('"') + SkipTo('"', fail_on="\n") + '"')
cfg_bool_eval = Literal("TRUE") | Literal("FALSE")

cfg_expr_eval = infix_notation(
    cfg_int_eval | cfg_str_eval | cfg_bool_eval | cfg_var_eval | cfg_unset_var_eval,
    [
        (one_of('-'), 1, OpAssoc.RIGHT),
        (one_of('* / \\'), 2, OpAssoc.LEFT),
        (one_of('+ -'), 2, OpAssoc.LEFT),
        (one_of('#'), 2, OpAssoc.LEFT),
        (one_of('^'), 2, OpAssoc.LEFT),
        (one_of('!'), 1, OpAssoc.RIGHT),
        (one_of('< <= == != >= >'), 2, OpAssoc.LEFT),
        (one_of('& |'), 2, OpAssoc.LEFT),
        (('?', ':'), 3, OpAssoc.RIGHT),
    ]
)
cfg_exprs_eval = Group(Suppress("(") + delimited_list(cfg_expr_eval, delim=Suppress(",")) + Suppress(")") | Empty())

cfg_goif_stmt_eval = Keyword("GOIF") + cfg_line_id + cfg_ws + cfg_expr_eval
cfg_into_stmt_eval = (cfg_expr_eval | cfg_empty) + cfg_ws + Keyword("INTO") + cfg_var
cfg_jump_stmt_eval = Keyword("JUMP") + cfg_line_id + cfg_exprs_eval + Group(cfg_handle_sbstmt)[...]
cfg_ret_stmt_eval = Keyword("RETURN") + cfg_exprs_eval

cfg_line = Opt(Group(
    cfg_go_stmt | cfg_goif_stmt_eval | cfg_jump_stmt_eval | cfg_throw_stmt |
    cfg_ret_stmt_eval | cfg_label_stmt | cfg_into_stmt_eval | cfg_load_stmt)) + Opt(cfg_comment)

# This can verify an ENTIRE thing of code.  If it doesn't match, your code is invalid.
cfg_code = delimited_list(cfg_line, delim=LineEnd()) + StringEnd()
