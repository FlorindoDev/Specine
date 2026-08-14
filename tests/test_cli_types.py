import argparse
import contextlib
import io
import unittest

from cli_types import positive_int


class PositiveIntTests(unittest.TestCase):
    def test_accepts_positive_integer(self):
        self.assertEqual(positive_int("1"), 1)

    def test_rejects_zero_and_negative_values(self):
        for value in ("0", "-1"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    argparse.ArgumentTypeError,
                    "must be greater than 0",
                ):
                    positive_int(value)

    def test_argparse_reports_invalid_max_iter(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--max_iter", type=positive_int)
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                parser.parse_args(["--max_iter", "0"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "argument --max_iter: must be greater than 0",
            stderr.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
