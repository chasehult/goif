#!/usr/bin/env python3

import re
import sys
from typing import Any, Dict, List, NamedTuple, Tuple, Union

from pyparsing import ParseException, ParseResults, ParserElement

__author__ = "Chase Hult"

from exceptions import GOIFError, GOIFException
from parser_pyp import cfg_asgn_stmt, cfg_asgn_stmt_eval, cfg_code, cfg_expr_var, cfg_go_stmt, cfg_goif_stmt, \
    cfg_jump_stmt, \
    cfg_lbl_ln, cfg_ret_stmt, cfg_str, \
    cfg_throw_stmt, cfg_unset_var


class Frame(NamedTuple):
    cur_ln: int
    cur_file: str
    vars: Dict[str, Any]
    handlers: Dict[str, int]


class GOIF:
    def __init__(self, code, *, debug_mode=False):
        self.strs = {}
        self.files = {}

        self.vars = {}
        self.call_stack = []
        self.debug = debug_mode

        code = self.preserve_strings(code)

        self.lines, self.labels = self.get_lines(code)

        self.cur_ln = self.labels['MAIN']
        self.cur_file = "MAIN"

        self.assert_code(code)

    def assert_code(self, code) -> None:
        @cfg_lbl_ln.add_parse_action
        def throw_on_bad_label(lines, _, pr):
            ln = len(lines.split("\n"))
            if pr[0] not in self.labels:
                raise GOIFError(f"Invalid label on line {ln}: {pr[0]}")

        try:
            assert cfg_code.parse_string(code) is not None
        except GOIFError as e:
            raise GOIFError(e.msg) from None

    def run(self, *args) -> None:
        self.setup(*args)
        self._run()

    def _run(self):
        while self.cur_ln <= max(self.lines, default=0):
            if self.cur_ln not in self.lines:
                self.cur_ln += 1
                continue

            line = self.lines[self.cur_ln]
            try:
                self.evaluate_statement(line)
            except GOIFError as e:
                raise GOIFError(f"Issue on line {self.cur_ln}. " + e.msg) from None

    def evaluate_input(self, line) -> None:
        line = self.preserve_strings(line)
        line = re.sub(r'\s+', ' ', line.split('%')[0].strip().upper())
        self.cur_ln = max(self.lines, default=0)
        try:
            self.evaluate_statement(line)
        except GOIFError as e:
            raise GOIFError(f"Issue on line {self.cur_ln}. " + e.msg) from None
        self._run()

    def evaluate_statement(self, line):
        if self.debug:
            print(self.cur_ln, self.restore_string(line, keep_quotes=True))

        if (tokens := self.try_match(cfg_go_stmt, line)):
            # GO
            label, = tokens
            self.cur_ln = self.label_to_ln(label)
        elif (tokens := self.try_match(cfg_goif_stmt, line)):
            # GOIF
            if isinstance(tokens, GOIFException):
                exc = tokens
                self.throw_exc(exc.name)
            else:
                label, expr = tokens
                if not isinstance(expr, bool):
                    raise GOIFError(f"GOIF expression does not evaluate to bool on line {self.cur_ln}")

                if expr:
                    self.cur_ln = self.label_to_ln(label)
                else:
                    self.cur_ln += 1
        elif (tokens := self.try_match(cfg_jump_stmt, line)):
            # JUMP
            label, args, *handlers = tokens
            self.push_frame(args, handlers)
            self.cur_ln = self.label_to_ln(label)
        elif (tokens := self.try_match(cfg_throw_stmt, line)):
            # THROW
            exception, = tokens
            self.throw_exc(exception)
        elif (tokens := self.try_match(cfg_ret_stmt, line)):
            # RETURN
            rets, = tokens
            self.pop_frame(rets)
            # Don't continue to increment after JUMP.  Maybe just do +1 in the stack func?
            self.cur_ln += 1
        elif self.try_match(cfg_asgn_stmt_eval, line):
            # INTO
            tokens = self.try_match(cfg_asgn_stmt, line)
            if isinstance(tokens, GOIFException):
                exc = tokens
                self.throw_exc(exc.name)
            else:
                expr, var = tokens
                if self.debug:
                    print(f"Storing {repr(expr)} into {var}.")
                self.set_variable(var, expr)
                self.cur_ln += 1
        else:
            raise GOIFError(f"Invalid statement: {repr(line)}")

        if isinstance(tokens, GOIFException):
            exc = tokens
            if self.debug:
                print(f"Failed expression.  Throwing {exc.name}")

    def label_to_ln(self, label):
        if label.startswith("^"):
            return int(label[1:])
        if label.startswith("~"):
            return self.cur_ln + int(label[1:])
        if label in self.labels:
            return self.labels[label]
        raise ValueError(f"Invalid label '{label}' on line {self.cur_ln}.")

    def set_variable(self, var: str, value: Any) -> None:
        if var == "STDERR":
            sys.stderr.write(str(value))
        elif var == "STDOUT":
            sys.stdout.write(str(value))
        elif var in ("STDIN"):
            raise GOIFError(f"You cannot read from {var}. (ln {self.cur_ln})")
        else:
            self.vars[var] = value

    def get_variable(self, pr: ParseResults) -> Any:
        var = pr[0]
        if var == "STDIN":
            return input()
        elif var in ("STDOUT", "STDERR"):
            raise GOIFError(f"You cannot write to {var}. (ln {self.cur_ln})")
        elif var in self.vars:
            return self.vars[var]
        raise GOIFError(f"Unknown variable {var} on line {self.cur_ln}")

    def push_frame(self, args: List, handlers: List[ParseResults]) -> None:
        handlers = {exc: self.label_to_ln(ln) for exc, ln in handlers}
        self.call_stack.append(Frame(self.cur_ln, self.cur_file, self.vars.copy(), handlers))
        if not args:
            for var in self.vars.copy():
                if not re.fullmatch(r'ARG\d+', var):
                    self.vars.pop(var)
        else:
            self.vars = {}
            for c, arg in enumerate(args, 1):
                self.vars[f'ARG{c}'] = arg

    def pop_frame(self, rets) -> None:
        if not self.call_stack:
            self.cur_ln = max(self.lines, default=0)
            return
        frame = self.call_stack.pop()
        self.cur_ln = frame.cur_ln
        cur_vars = frame.vars
        if not rets:
            for var, val in self.vars.copy().items():
                if re.fullmatch(r'RET\d+', var):
                    cur_vars[var] = val
        else:
            for c, ret in enumerate(rets, 1):
                cur_vars[f"RET{c}"] = ret
        self.vars = cur_vars

    def throw_exc(self, exc: str) -> None:
        if exc == "ERROR":
            raise GOIFError("Critical ERROR raised.")
        if not self.call_stack:
            raise GOIFException(exc)
        frame = self.call_stack.pop()
        if exc in frame.handlers:
            self.cur_ln = frame.handlers[exc]
        else:
            self.throw_exc(exc)

    def setup(self, *args) -> None:
        self.cur_ln = self.labels['MAIN']
        self.vars = {f"ARG{c + 1}": str(arg) for c, arg in enumerate(args)}
        cfg_str.set_parse_action(self.restore_string)
        cfg_expr_var.set_parse_action(self.get_variable)
        cfg_unset_var.set_parse_action(lambda pr: pr[0] not in self.vars)

    @staticmethod
    def try_match(cfg: ParserElement, string: str) -> Union[ParseResults, GOIFException, None]:
        try:
            return cfg.parse_string(string, parse_all=True)
        except GOIFException as e:
            return e
        except ParseException:
            return None

    @staticmethod
    def get_lines(code: str) -> Tuple[Dict[int, str], Dict[str, int]]:
        lines = {}
        labels = {}
        for ln, line in enumerate(code.split('\n'), 1):
            line = line.split('%')[0].strip().upper()
            if line.endswith(':'):
                label = line[:-1]
                if label in labels:
                    raise GOIFError(f"Label '{label}' appeared at least twice (lines {labels[label]} and {ln})")
                if not re.fullmatch(r'[\w.]+', label):
                    raise GOIFError(f"Invalid label name: '{label}'")
                labels[label] = ln
                continue
            if line:
                line = re.sub(r'\s+', ' ', line)
                lines[ln] = line
        labels.setdefault('MAIN', 0)
        return lines, labels

    def preserve_strings(self, code: str) -> str:
        idx = max(self.strs, default=0)

        def replace_and_increment(match) -> str:
            nonlocal idx
            self.strs[idx] = match.group(1).replace('\\n', '\n').replace('\\t', '\t') \
                .replace('\\"', '"').replace('\\b', '')
            idx += 1
            return f'"{idx - 1}"'

        def save_file(match) -> str:
            self.files[match.group(2).upper()] = match.group(1)
            return ""

        # Honestly, this is probably regular.  I'm too lazy to write w/o lookbehinds though.
        code = re.sub(r'(?<!\\)"((?:[^"\n]|(?<=\\)")*)(?<!\\)"', replace_and_increment, code)
        code = re.sub(r'^LOAD (.+) WITHNAME (.+)$', save_file, code, re.IGNORECASE)
        return code

    def restore_string(self, line: Union[str, ParseResults], *, keep_quotes=False) -> str:
        if isinstance(line, ParseResults):
            line = line[0]

        def restore(match):
            string = self.strs[int(match.group(1))]
            if keep_quotes:
                string = repr(string)
            return string

        return re.sub(r'"(\d+)"', restore, line)


if __name__ == "__main__":
    offset = 0
    interactive = debug = False
    if sys.argv[1].startswith("-"):
        flags = sys.argv[1]
        offset = 1
        if 'i' in flags:
            interactive = True
        if 'd' in flags:
            debug = True

    if not interactive:
        goif_code = GOIF(open(sys.argv[1 + offset]).read(), debug_mode=debug)
        goif_code.run(*sys.argv[2+offset:])
    else:
        if len(sys.argv) < 3:
            goif_code = GOIF('', debug_mode=debug)
        else:
            goif_code = GOIF(open(sys.argv[1 + offset]).read(), debug_mode=debug)
        goif_code.setup(*sys.argv[2+offset:])
        cur_line = ""
        while cur_line.upper() != "RETURN":
            cur_line = input('>>> ')
            goif_code.evaluate_input(cur_line)
