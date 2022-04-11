__author__ = "Kendyl Reisinger"

# This function will take in an operator and one or two operands in the form of ('<operator>', <operand1>, <operand2>).
# The function of the operator will then be performed and the result returned.
from exceptions import GOIFException, GOIFRuntimeError


def Operate(optr, *args):
    # addition
    if optr == '+':
        if isinstance(args[0], int) and isinstance(args[1], int):
            return args[0] + args[1]
        else:
            raise GOIFRuntimeError("Operands must both be integers.")
    # subtraction
    elif optr == '-':
        if len(args) == 1:
            if isinstance(args[0], int):
                return -args[0]
        elif isinstance(args[0], int) and isinstance(args[1], int):
            return args[0] - args[1]
        else:
            raise GOIFRuntimeError("Operands must be integers.")
    # multiplication
    elif optr == '*':
        if isinstance(args[0], int) and isinstance(args[1], int):
            return args[0] * args[1]
        else:
            raise GOIFRuntimeError("Operands must both be integers.")
    # less than
    elif optr == '<':
        if isinstance(args[0], int) and isinstance(args[1], int):
            return args[0] < args[1]
        else:
            raise GOIFRuntimeError("Operands must both be integers.")
    # greater than
    elif optr == '>':
        if isinstance(args[0], int) and isinstance(args[1], int):
            return args[0] > args[1]
        else:
            raise GOIFRuntimeError("Operands must both be integers.")
    # less than or equal to
    elif optr == '<=':
        if isinstance(args[0], int) and isinstance(args[1], int):
            return args[0] <= args[1]
        else:
            raise GOIFRuntimeError("Operands must both be integers.")
    # greater than or equal to
    elif optr == '>=':
        if isinstance(args[0], int) and isinstance(args[1], int):
            return args[0] >= args[1]
        else:
            raise GOIFRuntimeError("Operands must both be integers.")
    # equality
    elif optr == '==':
        if isinstance(args[0], int) and isinstance(args[1], int):
            return args[0] == args[1]
        if isinstance(args[0], str) and isinstance(args[1], str):
            return args[0] == args[1]
        else:
            raise GOIFRuntimeError("Operands must both be integers or must both be strings.")
    # less than or equal to
    elif optr == '!=':
        if isinstance(args[0], int) and isinstance(args[1], int):
            return args[0] != args[1]
        if isinstance(args[0], str) and isinstance(args[1], str):
            return args[0] != args[1]
        else:
            raise GOIFRuntimeError("Operands must both be integers or must both be strings.")
    # integer division
    elif optr == '/':
        if isinstance(args[0], int) and isinstance(args[1], int):
            if args[1] == 0:
                raise GOIFException("OP_FAIL")
            return args[0] // args[1]
        else:
            raise GOIFRuntimeError("Operand must both be integers.")
    # modulus
    elif optr == '\\':
        if isinstance(args[0], int) and isinstance(args[1], int):
            if args[1] == 0:
                raise GOIFException("OP_FAIL")
            return args[0] % args[1]
        else:
            raise GOIFRuntimeError("Operand must both be integers.")
    # boolean not
    elif optr == '!':
        if isinstance(args[0], bool):
            return not args[0]
        else:
            raise GOIFRuntimeError("Operand must be a boolean.")
    # boolean and
    elif optr == '&':
        if isinstance(args[0], bool) and isinstance(args[1], bool):
            return args[0] and args[1]
        else:
            raise GOIFRuntimeError("Operands must both be booleans.")
    elif optr == '|':
        if isinstance(args[0], bool) and isinstance(args[1], bool):
            return args[0] or args[1]
        else:
            raise GOIFRuntimeError("Operands must both be booleans.")
    # indexing
    elif optr == '#':
        if isinstance(args[0], str) and isinstance(args[1], int):
            if args[1] > len(args[0]):
                raise GOIFException("OP_FAIL")
            return args[0][args[1]-1]
        else:
            raise GOIFRuntimeError("First operand must be a string and second operand must be an integer.")
    # concatenate
    elif optr == '^':
        if isinstance(args[0], str) and isinstance(args[1], str):
            return args[0] + args[1]
        else:
            raise GOIFRuntimeError("Operands must both be strings.")
    # ternary operator
    elif optr == '?':
        if isinstance(args[0], bool):
            if args[0]:
                return args[1]
            else:
                return args[2]
        else:
            raise GOIFRuntimeError("First operand must be bool.")
