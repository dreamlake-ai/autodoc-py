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


if __name__ == '__main__':
    unittest.main()
