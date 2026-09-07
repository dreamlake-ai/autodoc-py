import unittest
from autodoc_py import prose
from autodoc_py.docstrings import format_docstring


class DocstringTests(unittest.TestCase):
    def test_partial_example_stays_code(self):
        raw = '''Inject defaults.

Args:
    config_class: A class with defaults
    method (bool): Whether to wrap as a method
        Continued description.

Example:
    class Config:
        lr: float = 0.01

    @proto.partial(Config)
    def train() -> None:
        print(f"Rate: {Config.lr}")

    # Supports direct attribute modification:
    Config.lr = 0.001
    train()

Returns:
    Decorated function with config values injected.
'''
        actual = prose(format_docstring(raw))
        self.assertIn('- `config_class`: A class with defaults', actual)
        self.assertIn('- `method (bool)`: Whether to wrap as a method\n  Continued description.', actual)
        self.assertIn('```python\nclass Config:', actual)
        self.assertIn('def train() -> None:', actual)
        self.assertIn('print(f"Rate: {Config.lr}")', actual)
        self.assertIn('# Supports direct attribute modification:', actual)
        self.assertIn('train()\n```\n\n**Returns**', actual)
        self.assertNotIn('&#123;Config.lr', actual)

    def test_markdown_and_ordinary_indentation_preserved(self):
        raw = 'A paragraph.\n\n- First item\n    - Nested item\n\n    Ordinary indented prose.\n\n```python\nArgs:\n    literal = {1}\n```'
        self.assertEqual(format_docstring(raw), raw)

    def test_fenced_example_not_double_wrapped(self):
        raw = 'Examples:\n    ```python\n    print({"a": 1})\n    ```\n\nNext paragraph.'
        actual = format_docstring(raw)
        self.assertEqual(actual.count('```'), 2)
        self.assertIn('```python\nprint({"a": 1})\n```', actual)
        self.assertTrue(actual.endswith('Next paragraph.'))

    def test_example_markdown_list_is_not_code(self):
        self.assertEqual(format_docstring('Examples:\n    - First case\n    - Second case'), '**Examples**\n\n- First case\n- Second case')

    def test_literal_backtick_fence_in_example(self):
        actual = prose(format_docstring('Example:\n    text = "```"\n    value = {"key": 1}'))
        self.assertIn('````python\ntext = "```"', actual)
        self.assertIn('value = {"key": 1}', actual)
        self.assertTrue(actual.endswith('````'))

    def test_numbered_list_examples_preserve_comments_and_braces(self):
        raw = 'Four syntaxes:\n\n1. Assignment:\n    api_key: str = EnvVar("API_KEY")\n    # Or function syntax:\n    values = {"key": api_key}\n\n2. Another case:\n    result = EnvVar @ "NAME"\n\nNormal prose.'
        actual = prose(format_docstring(raw))
        self.assertIn('   ```python\n   api_key: str', actual)
        self.assertIn('   # Or function syntax:', actual)
        self.assertIn('values = {"key": api_key}', actual)
        self.assertEqual(actual.count('```python'), 2)
        self.assertTrue(actual.endswith('Normal prose.'))

    def test_rst_literal_block_and_non_code_prose(self):
        actual = format_docstring('Run this::\n\n    # Literal comment\n    arbitrary literal text\n\nThen continue.')
        self.assertIn('```python\n# Literal comment\narbitrary literal text\n```', actual)
        raw = 'Notes:\n\n    A normal paragraph with words.\n    Another sentence here.\n\n- Parent\n    - Child'
        self.assertEqual(format_docstring(raw), raw)

    def test_numbered_examples_after_field_extraction(self):
        from autodoc_py.presentation import documentation
        raw = 'Reader.\n\n1. Matmul:\n    batch_size: int = EnvVar @ "BATCH_SIZE"\n\n2. Or operation:\n    api_key: str = EnvVar @ "API_KEY" | "default"\n    # Or function syntax:\n    api_key: str = EnvVar("API_KEY", default="default")\n\nArgs:\n    name: Variable name'
        narrative, *_ = documentation(raw)
        actual = prose(format_docstring(narrative))
        self.assertEqual(actual.count('```python'), 2)
        self.assertIn('   # Or function syntax:', actual)
        self.assertNotIn('Args:', actual)


if __name__ == '__main__':
    unittest.main()
