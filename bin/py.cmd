@echo off
rem Windows twin of bin/py: runs the first working Python 3.9+ (python3, python, py -3) with these arguments.
rem .mcp.json names bin/py without an extension, so Windows finds this file through PATHEXT and needs no bash on PATH;
rem macOS and Linux run bin/py through its shebang. python3 may be the Microsoft Store stub, which fails the check.
setlocal
for %%P in (python3 python) do (
  %%P -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && (
    %%P %*
    exit /b
  )
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && (
  py -3 %*
  exit /b
)
echo bindle: no Python 3.9+ found (tried python3, python, py -3) 1>&2
exit /b 1
