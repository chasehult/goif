#!/usr/bin/env python3

import os.path
import re
import sys
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

from pyparsing import ParseException, ParseResults, ParserElement

__author__ = "Chase Hult"

from exceptions import GOIFCompileError, GOIFException, GOIFRuntimeError
from parser_pyp import SpecialValues, cfg_into_stmt, cfg_into_stmt_eval, cfg_code, cfg_expr_var, cfg_go_stmt, \
    cfg_goif_stmt, cfg_jump_stmt, cfg_line_id, cfg_ret_stmt, cfg_str, cfg_throw_stmt, cfg_unset_var


class Frame(NamedTuple):
    cur_ln: int
    cur_file: int
    vars: Dict[str, Union[bool, str, int]]
    handlers: Dict[str, Tuple[int, int]]


class GOIF:
    def __init__(self, fp: Optional[str], *, debug_mode: bool = False, unsafe_jump: bool = False):

        self.cur_file: int = 0
        self.cur_ln: int = 0
        self.vars: Dict[str, Union[bool, str, int]] = {}
        self.call_stack: List[Frame] = []

        self.files: Dict[int, Dict[
            str, int]] = {}  # Per-file file identifiers to file ids (ik identifier = id but i swear they're different)
        self.lines: Dict[int, Dict[int, str]] = {}  # Per-file line numbers to statements
        self.labels: Dict[int, Dict[str, int]] = {}  # Per-file line labels to line numbers

        self.strs: Dict[int, str] = {}  # Preserved strings

        self.debug = debug_mode
        self.fid_to_str = {1: os.path.basename(fp or "INPUT"), 2: 'STANDARD LIBRARY'}

        self.unsafe_jump = unsafe_jump

        self.fn_map = {}
        self.compile(fp)

        self.cur_ln = self.labels[1]['MAIN']
        self.cur_file = 1

    def assert_code(self, code) -> None:
        """Assert that an entire code file is valid.

        This must be done before removing comments and labels, but after preserving strings
        """

        @cfg_line_id.set_parse_action
        def throw_on_bad_label(lines, _, pr):
            ln = len(lines.split("\n"))
            fname, lid = pr[0]
            if fname is not None:
                if fname not in self.files[self.cur_file]:
                    raise GOIFCompileError(f"Invalid file: '{fname}'."
                                           + self.get_current_state())
                c_fid = self.files[self.cur_file][fname]
            else:
                c_fid = self.cur_file

            if re.fullmatch(r'[~^]\d+', lid):
                return

            if lid not in self.labels[c_fid]:
                raise GOIFCompileError(f"Invalid label: '{fname + ':' if fname else ''}{lid}'."
                                       + self.get_current_state())

        try:
            assert cfg_code.parse_string(code) is not None
        except GOIFCompileError as e:
            raise e from None

    def get_current_state(self, cur_ln = None, cur_file = None) -> str:
        cur_ln = cur_ln or self.cur_ln
        cur_file = cur_file or self.cur_file
        return f" (line {cur_ln if cur_ln != float('inf') else 'N/A'}," \
               f" file '{self.fid_to_str[cur_file]}')"

    def run(self, *args) -> None:
        self.setup(*args)
        if self.debug:
            print("Loaded Files:")
            for fid, fp in self.fid_to_str.items():
                print(f" {fid} - {fp}")
            print()
        self._run()

    def _run(self):
        while self.cur_ln <= max(self.lines[self.cur_file], default=0) or self.call_stack:
            if self.cur_ln > max(self.lines[self.cur_file], default=0):
                self.pop_frame()
                continue

            if self.cur_ln not in self.lines[self.cur_file]:
                self.cur_ln += 1
                continue

            line = self.lines[self.cur_file][self.cur_ln]
            try:
                self.evaluate_statement(line)
            except GOIFRuntimeError as e:
                e.msg += self.get_current_state()
                raise e from None

    def evaluate_input(self, line) -> None:
        line = self.preserve_strings(line)
        self.cur_ln = float('inf')
        try:
            if (match := re.fullmatch(r'\s*LOAD\s+(\S+)\s+(\S+)\s*', line, re.I)):
                # This is a LOAD statement.  We need to handle this specially.
                self.files[1][match.group(2).upper()] = self.compile(match.group(1))
            else:
                line = re.sub(r'\s+', ' ', line.split('%')[0].strip().upper())
                self.evaluate_statement(line)
        except GOIFRuntimeError as e:
            e.msg += self.get_current_state()
            raise e from None
        self._run()

    def evaluate_statement(self, line):
        """Evaluate one GOIF statement."""
        if self.debug:
            print(f"[{len(self.call_stack) + 1}]"
                  f" #{self.cur_file}{'-' + str(self.cur_ln) if self.cur_ln != float('inf') else ''}:"
                  f" {self.restore_string(line, keep_quotes=True)}")

        if (tokens := self.try_match(cfg_go_stmt, line)):
            # GO
            label, = tokens
            self.cur_file, self.cur_ln = self.label_to_ln(label)
        elif (tokens := self.try_match(cfg_goif_stmt, line)):
            # GOIF
            if isinstance(tokens, GOIFException):
                exc = tokens
                self.throw_exc(exc.name)
            elif isinstance(tokens, ParseResults):
                label, expr = tokens
                if not isinstance(expr, bool):
                    raise GOIFRuntimeError(f"GOIF expression does not evaluate to bool."
                                           + self.get_current_state())

                if expr:
                    self.cur_file, self.cur_ln = self.label_to_ln(label)
                else:
                    self.cur_ln += 1
        elif (tokens := self.try_match(cfg_jump_stmt, line)):
            # JUMP
            label, args, *handlers = tokens
            self.push_frame(args, handlers)
            self.cur_file, self.cur_ln = self.label_to_ln(label)
        elif (tokens := self.try_match(cfg_throw_stmt, line)):
            # THROW
            exception, = tokens
            self.throw_exc(exception)
        elif (tokens := self.try_match(cfg_ret_stmt, line)):
            # RETURN
            rets, = tokens
            self.pop_frame(rets)
        elif self.try_match(cfg_into_stmt_eval, line):
            # INTO
            try:
                tokens = self.try_match(cfg_into_stmt, line)
            except GOIFRuntimeError as e:
                raise GOIFRuntimeError(e.msg + self.get_current_state()) from None

            if isinstance(tokens, GOIFException):
                exc = tokens
                self.throw_exc(exc.name)
            else:
                expr, var = tokens
                if self.debug:
                    if expr is SpecialValues.Empty:
                        print(f"Unsetting {var}.")
                    else:
                        print(f"Storing {repr(expr)} into {var}.")
                self.set_variable(var, expr)
                self.cur_ln += 1
        else:
            raise GOIFRuntimeError(f"Invalid statement: {repr(line)}."
                                   + self.get_current_state())

        if self.debug and isinstance(tokens, GOIFException):
            exc = tokens
            print(f"Failed expression.  Throwing {exc.name}")

    def label_to_ln(self, label) -> Tuple[int, int]:
        """Convert a label identifier to a file id and line number.."""
        file_id, line_id = label
        if file_id is None:
            file = self.cur_file
        else:
            file = self.files[self.cur_file][file_id]

        if line_id.startswith("^"):  # Absolute
            return file, int(line_id[1:])
        if line_id.startswith("~"):  # Relative
            return file, self.cur_ln + int(line_id[1:])
        if line_id in self.labels[file]:  # Line Label
            return file, self.labels[file][line_id]
        raise GOIFCompileError(f"Invalid label '{line_id}'."
                               + self.get_current_state())

    def set_variable(self, var: str, value: Any) -> None:
        """Set a GOIF variable to the current namespace.

        This is used in INTO statements."""
        if value is SpecialValues.Empty:
            if var in self.vars:
                self.vars.pop(var)
        elif var == "STDERR":
            sys.stderr.write(str(value))
        elif var == "STDOUT":
            sys.stdout.write(str(value))
        elif var in ("STDIN",):
            raise GOIFRuntimeError(f"You cannot read from {var}."
                                   + self.get_current_state())
        else:
            self.vars[var] = value

    def get_variable(self, pr: ParseResults) -> Any:
        """Get a GOIF variable from the current namespace.

        This is used in expressions."""
        var = pr[0]
        if var == "STDIN":
            return input()
        elif var in ("STDOUT", "STDERR"):
            raise GOIFRuntimeError(f"You cannot write to {var}."
                                   + self.get_current_state())
        elif var in self.vars:
            return self.vars[var]
        raise GOIFRuntimeError(f"Unknown variable {var}."
                               + self.get_current_state())

    def push_frame(self, args: List, handlers: List[ParseResults]) -> None:
        """Push the current frame onto the call stack.

        This is called in a JUMP statement"""
        if len(self.call_stack) >= 255 and not self.unsafe_jump:
            raise GOIFRuntimeError("Call stack overflow. Possible infinite loop?"
                                   " Run with unsafe_jump (-j) if this is intended.")
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

    def pop_frame(self, rets: Optional[ParseResults] = None) -> None:
        """Pop from the call stack

        This is called in a RETURN statement or when a file is over."""
        if not self.call_stack:
            self.cur_ln = float('inf')
            return
        frame = self.call_stack.pop()
        self.cur_file = frame.cur_file
        self.cur_ln = frame.cur_ln + 1
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
        """Throw a GOIF exception.

        This is called on some bad expressions or in an explicit THROW statement"""
        if exc == "ERROR":
            raise GOIFRuntimeError("ERROR thrown." + self.get_current_state())
        jumps = ""
        while self.call_stack:
            frame = self.call_stack.pop()
            jumps += f" from JUMP{self.get_current_state(frame.cur_ln, frame.cur_file)}"
            if exc in frame.handlers:
                self.cur_file, self.cur_ln = frame.handlers[exc]
                self.vars = frame.vars
                return
        raise GOIFException(exc + self.get_current_state() + jumps)

    def setup(self, *args) -> None:
        """This resets everything to run a file again which is no longer supported due to ease of command line use."""
        self.cur_file = 1
        self.cur_ln = self.labels[1]['MAIN']
        self.vars = {f"ARG{c + 1}": str(arg) for c, arg in enumerate(args)}
        cfg_str.set_parse_action(self.restore_string)
        cfg_expr_var.set_parse_action(self.get_variable)
        cfg_unset_var.set_parse_action(lambda pr: pr[0] not in self.vars)

    def try_match(self, cfg: ParserElement, string: str) -> Union[ParseResults, GOIFException, None]:
        """PyParsing raises an exception instead of just failing on an invalid parse.  This fixes that."""
        try:
            return cfg.parse_string(string, parse_all=True)
        except GOIFException as e:
            return e
        except ParseException:
            return None
        except GOIFRuntimeError as e:
            raise GOIFRuntimeError(e.msg + self.get_current_state())

    def compile(self, root: Optional[str]) -> int:
        """Compile a GOIF file.

        The return value is the FId of the root which is 1 unless we're in interactive mode.
        """
        root = os.path.abspath(root) if root is not None else None
        if root in self.fn_map:
            return self.fn_map[root]

        codes = {}

        idx = max(self.files, default=0) + 2

        fp_root = os.path.dirname(root) if root is not None else ''
        std = os.path.abspath(os.path.join(os.path.dirname(__file__), 'std.goif'))

        seen = set(self.fn_map.values())
        self.fn_map.update({root: idx - 1, std: 2})
        if idx == 2:  # Don't overwrite the standard library
            idx += 1

        files = {root, std}
        while files:
            fp = files.pop()
            fid = self.fn_map[fp]
            if fp is None and fid == 1:
                # We're in interactive mode, so we don't have a MAIN file!
                self.files[1] = {"MAIN": 1, "STD": 2}
                self.lines[1] = {}
                self.labels[1] = {'MAIN': 1}
                continue

            if "/" not in fp:
                # Unless specified, we assume all modules are in the same directory as MAIN
                fp = os.path.join(fp_root, fp)

            fp = os.path.abspath(fp)
            if fp in seen:
                continue
            seen.add(fp)

            # Prepare the curretn code file for parsing
            code = self.preserve_strings(open(fp).read())
            codes[fid] = code  # We keep a copy of the code to check for validity later
            code, links = self.get_files(code)

            # Add all loads to our queue.
            self.files[fid] = {"MAIN": 1, "STD": 2}
            for fid_link, fp_link in links.items():
                fp_link = os.path.join(fp_root, fp_link) if "/" not in fp_link else fp_link
                if fp_link not in self.fn_map:
                    self.fn_map[fp_link] = idx
                    self.fid_to_str[idx] = os.path.basename(fp_link)
                    idx += 1
                self.files[fid][fid_link] = self.fn_map[fp_link]
                files.add(fp_link)

            # Parsing step for lines and labels
            f_lines = {}
            f_labels = {}
            for ln, line in enumerate(code.split('\n'), 1):
                line = line.split('%')[0].strip().upper()
                if line.endswith(':'):
                    label = line[:-1]
                    if label in f_labels:
                        raise GOIFCompileError(f"Label '{label}' appeared at least twice in file {self.fid_to_str[fid]}"
                                               f" (lines {f_labels[label]} and {ln})")
                    if not re.fullmatch(r'[\w.]+', label):
                        raise GOIFCompileError(f"Invalid label name in file {self.fid_to_str[idx]}: '{label}'")
                    f_labels[label] = ln
                    continue
                if line:
                    line = re.sub(r'\s+', ' ', line)
                    f_lines[ln] = line
            f_labels.setdefault('MAIN', 1)
            self.lines[fid] = f_lines
            self.labels[fid] = f_labels

        # Check all files compiletime to make sure they're all valid
        for fid, code in codes.items():
            self.cur_file = fid
            self.assert_code(code)
        self.cur_file = 1
        return self.fn_map[root]

    def preserve_strings(self, code: str) -> str:
        """Replace strings in a file with an identifier to recall them later.  This makes parsing easier."""
        idx = max(self.strs, default=0) + 1

        def replace_and_increment(match) -> str:
            nonlocal idx
            self.strs[idx] = match.group(1).replace('\\n', '\n').replace('\\t', '\t') \
                .replace('\\"', '"').replace('\\0', '\0')
            idx += 1
            return f'"{idx - 1}"'

        # Honestly, this is probably regular.  I'm too lazy to write w/o lookbehinds though.
        code = re.sub(r'(?<!\\)"((?:[^"\n]|(?<=\\)")*)(?<!\\)"', replace_and_increment, code)
        return code

    def get_files(self, code: str) -> Tuple[str, Dict[str, str]]:
        """Get the loaded files out of a code block"""
        files = {}

        def save_file(match) -> str:
            files[match.group(2).upper()] = match.group(1)
            return ""

        code = re.sub(r'^\s*LOAD\s+(\S+)\s+(\S+)\s*$', save_file, code, flags=re.I + re.M)
        return code, files

    def restore_string(self, line: Union[str, ParseResults], *, keep_quotes=False) -> str:
        """Recall a preserved string identifier"""
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
    interactive = debug = unsafe_jump = False
    if len(sys.argv) > 1 and sys.argv[1].startswith("-"):
        flags = sys.argv[1]
        offset = 1
        if 'i' in flags:
            interactive = True
        if 'd' in flags:
            debug = True
        if 'j' in flags:
            unsafe_jump = True

    if not sys.argv[1 + offset:] and not interactive:
        print("Usage:\n goif.py [-dij] path/to/file.goif [arg ...]\n goif.py -i[dj]")
        exit(1)

    if not interactive:
        goif_code = GOIF(sys.argv[1 + offset], debug_mode=debug, unsafe_jump=unsafe_jump)
        goif_code.run(*sys.argv[2 + offset:])
    else:
        if len(sys.argv) < 3:
            goif_code = GOIF(None, debug_mode=debug, unsafe_jump=unsafe_jump)
        else:
            goif_code = GOIF(sys.argv[1 + offset], debug_mode=debug, unsafe_jump=unsafe_jump)
        goif_code.setup(*sys.argv[2 + offset:])
        cur_line = ""
        while cur_line.upper() != "RETURN":
            cur_line = input('>>> ')
            if cur_line:
                goif_code.evaluate_input(cur_line)
