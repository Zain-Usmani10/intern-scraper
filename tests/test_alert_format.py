"""Locks the email and Telegram formats to the approved examples in sample/.

Run: python -m unittest discover tests
To change the format on purpose, edit scripts/alerts.py, then run
python scripts/make_samples.py and commit the new samples.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import make_samples  # noqa: E402


class AlertFormat(unittest.TestCase):
    def test_matches_approved_samples(self):
        for name, content in make_samples.samples().items():
            with self.subTest(file=name):
                approved = (make_samples.SAMPLE_DIR / name).read_text(encoding="utf-8")
                self.assertEqual(content, approved, f"{name} no longer matches sample/{name}")


if __name__ == "__main__":
    unittest.main()
