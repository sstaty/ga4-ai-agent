EXECUTE_PYTHON_TOOL = {
    "name": "execute_python",
    "description": (
        "Run Python code in an isolated Docker sandbox. "
        "Available libraries: pandas, matplotlib, numpy, scipy. "
        "No network access. Embed any GA4 data as literals in the code. "
        "Use print() to output results."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
        },
        "required": ["code"],
    },
}
