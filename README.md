# GOIF

GOIF is an interpreted language, so to run a .goif file, you have to run it through the interpreter.  The syntax to run GOIF code is

```bash
python /path/to/goif.py [-idj] /path/to/code.goif [args ...]
```

The flags are:
 
 * `i`nterpreted mode.  This only compiles any code you enter without running any of it.  It runs any command line input you put in after.  Use `RETURN` to exit.  If you run interpreted mode, you don't need to input a .goif file.  
 * `d`ebug mode.  This gives detailed feedback on each line that runs.  The format is `[c] #f-l stmt` where `c` is how many layers deep in the call stack you are, `f` is the file id which is printed at the beginning of the code, `l` is the line number, and `stmt` is the actual statement being run.  It also gives helpful information when an expression is evaluated or when an exception is thrown.
 * `j`ump safety removal.  Normally, you can only go 255 layers deep to avoid infinite loops, but if you're working with complex or highly recursive code, you may want to enable this option to allow infinite depth.

The args put in are stored into string variables named `arg#` where `#` is the 1-indexed position of the argument.
