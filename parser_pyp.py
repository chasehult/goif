from pyparsing import Char, Combine, Empty, Group, Keyword as _Keyword, LineEnd, Literal, OpAssoc, Opt, ParseResults, \
    ParserElement, Regex, StringEnd, Suppress, White, Word, alphanums, alphas, common, delimited_list, infix_notation, \
    nums, one_of

from operator_exprs import Operate

__author__ = "Chase Hult"


def Keyword(kw):
    return Suppress(_Keyword(kw, caseless=True))


ParserElement.set_default_whitespace_chars(' \t')

KEYWORDS = [
    "INTO", "GO", "GOIF", "JUMP", "THROW", "RETURN", "HANDLE", "LOAD", "WITHNAME",
    "TRUE", "FALSE",
]


def not_keyword(tokens):
    var, = tokens
    return var.strip() not in KEYWORDS


cfg_ws = Suppress(White())

cfg_var = common.identifier
cfg_var.add_condition(not_keyword)
cfg_expr_var = cfg_var.copy()
cfg_unset_var = Combine(Suppress('@') + Char(alphas + '_') + Char(alphanums + '_')[...])

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
            return Operate(*expr)
        elif num == 2:
            a1, op, *a2 = expr
            return Operate(op, a1, _fold(a2))
        elif num == 3:
            a1, op, a2, _, a3 = expr
            return Operate(op, a1, a2, a3)

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

cfg_file_id = Word(alphanums + '_')
# cfg_line_id = Group(Opt(cfg_file_id + Suppress(":")).set_parse_action(lambda pr: pr or "MAIN") + cfg_line_no)
cfg_line_id = cfg_line_no

cfg_exception = Word(alphanums + '_')

cfg_handle_sbstmt = Keyword("HANDLE") + cfg_exception + cfg_ws + cfg_line_id

cfg_goif_file = Word(alphanums + '_./ ')

cfg_label_stmt = Combine(cfg_lbl_ln + ':')
cfg_load_stmt = Keyword("LOAD") + cfg_goif_file + Keyword("ASNAME") + cfg_file_id
cfg_go_stmt = Keyword("GO") + cfg_line_id
cfg_goif_stmt = Keyword("GOIF") + cfg_line_id + cfg_ws + cfg_expr
cfg_jump_stmt = Keyword("JUMP") + cfg_line_id + cfg_exprs + Group(cfg_handle_sbstmt)[...]
cfg_throw_stmt = Keyword("THROW") + cfg_exception
cfg_ret_stmt = Keyword("RETURN") + cfg_exprs
cfg_asgn_stmt = cfg_expr + cfg_ws + Keyword("INTO") + cfg_var

cfg_comment = Suppress(Literal("%") + Regex('[^\n]*'))


# Evaluation (Inert)
cfg_var_eval = Combine(Char(alphas + '_') + Char(alphanums + '_')[...])
cfg_var_eval.add_condition(not_keyword)
cfg_unset_var_eval = Combine(Suppress('@') + cfg_var_eval)

cfg_int_eval = common.signed_integer
cfg_str_eval = Combine('"' + Word(nums) + '"')
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
cfg_asgn_stmt_eval = cfg_expr_eval + cfg_ws + Keyword("INTO") + cfg_var
cfg_jump_stmt_eval = Keyword("JUMP") + cfg_line_id + cfg_exprs_eval + Group(cfg_handle_sbstmt)[...]
cfg_ret_stmt_eval = Keyword("RETURN") + cfg_exprs_eval


cfg_line = Opt(Group(
    cfg_go_stmt | cfg_goif_stmt_eval | cfg_jump_stmt_eval | cfg_throw_stmt |
    cfg_ret_stmt_eval | cfg_label_stmt | cfg_asgn_stmt_eval | cfg_file_id)) + Opt(cfg_comment)
cfg_code = delimited_list(cfg_line, delim=LineEnd()) + StringEnd()


def normalize(x):
    return [normalize(list(v)) if isinstance(v, (list, ParseResults)) else v for v in x]
