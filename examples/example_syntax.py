#!/usr/bin/env python3
"""Example usage of PromptKit with syntax highlighting."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptkit import (  # noqa: E402
    WordCompleter,
    Prompt,
    Highlighter,
)


def main():
    """Run the example prompt with syntax highlighting."""

    # Python keywords and built-in functions
    python_keywords = [
        "def", "class", "if", "else", "elif", "for", "while",
        "try", "except", "finally", "with", "import", "from",
        "return", "yield", "lambda", "pass", "break", "continue",
        "and", "or", "not", "in", "is", "None", "True", "False"
    ]

    python_functions = [
        "print", "len", "range", "str", "int", "float", "list",
        "dict", "set", "tuple", "open", "input", "type", "isinstance",
        "enumerate", "zip", "map", "filter", "sorted", "sum", "max", "min"
    ]

    python_modules = [
        "os", "sys", "json", "re", "math", "random", "datetime",
        "collections", "itertools", "functools", "pathlib", "typing"
    ]

    # Combine all words
    all_words = python_keywords + python_functions + python_modules

    # Create descriptions
    descriptions = {
        "def": "Define a function",
        "class": "Define a class",
        "if": "Conditional statement",
        "else": "Else clause",
        "elif": "Else if clause",
        "for": "For loop",
        "while": "While loop",
        "try": "Try block for exception handling",
        "except": "Exception handler",
        "finally": "Finally block",
        "with": "Context manager",
        "import": "Import module",
        "from": "Import from module",
        "return": "Return from function",
        "yield": "Yield from generator",
        "lambda": "Anonymous function",
        "print": "Print to stdout",
        "len": "Get length",
        "range": "Generate range",
        "str": "Convert to string",
        "int": "Convert to integer",
        "float": "Convert to float",
        "list": "Create list",
        "dict": "Create dictionary",
        "set": "Create set",
        "tuple": "Create tuple",
        "open": "Open file",
        "input": "Get user input",
        "type": "Get type",
        "isinstance": "Check instance type",
        "enumerate": "Enumerate items",
        "zip": "Zip iterables",
        "map": "Map function",
        "filter": "Filter items",
        "sorted": "Sort items",
        "sum": "Sum items",
        "max": "Get maximum",
        "min": "Get minimum",
        "os": "Operating system interface",
        "sys": "System-specific parameters",
        "json": "JSON encoder/decoder",
        "re": "Regular expressions",
        "math": "Mathematical functions",
        "random": "Random number generation",
        "datetime": "Date and time",
        "collections": "Specialized container datatypes",
        "itertools": "Functions creating iterators",
        "functools": "Higher-order functions",
        "pathlib": "Object-oriented filesystem paths",
        "typing": "Type hints support",
    }

    # Create type dictionary for syntax highlighting
    types = {}
    for keyword in python_keywords:
        types[keyword] = "keyword"
    for func in python_functions:
        types[func] = "function"
    for mod in python_modules:
        types[mod] = "module"

    # Create completer with type information
    completer = WordCompleter(
        all_words,
        meta_dict=descriptions,
        type_dict=types,
        ignore_case=True
    )

    # Create highlighter with monokai style
    highlighter = Highlighter(
        style="monokai",
        truecolor=True,  # Enable truecolor
        language="python"
    )

    # Print instructions
    print("PromptLSP Library Demo - Syntax Highlighting")
    print("=" * 60)
    print("Features:")
    print("  • Syntax highlighting for Python keywords, functions, modules")
    print("  • Truecolor support (24-bit colors)")
    print("  • Monokai color theme")
    print("  • wcwidth for proper Unicode character width")
    print()
    print("Instructions:")
    print("• Type Python keywords (def, class, if, etc.)")
    print("• Type Python functions (print, len, range, etc.)")
    print("• Type Python modules (os, sys, json, etc.)")
    print("• TAB   : Buka popup / Pindah ke bawah.")
    print("• ENTER : Pilih item / Submit.")
    print("• SPACE : Menutup popup.")
    print("• Arrows: Navigasi kiri/kanan/atas/bawah.")
    print("=" * 60)
    print()

    # Create prompt instance with syntax highlighting
    prompt = Prompt(
        completer,
        prompt="python >>> ",
        box_style="rounded",
        highlighter=highlighter
    )

    try:
        while True:
            # Run prompt loop
            result = prompt.run()
            print(f"You entered: {result}")

            # Reset state for next input
            prompt.input_buffer = ""
            prompt.cursor_pos = 0
            prompt.show_box = False
            prompt.selected_idx = 0
            prompt.scroll_offset = 0

    except KeyboardInterrupt:
        print("\nGoodbye.")


if __name__ == "__main__":
    main()
