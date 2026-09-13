import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "web" / "email" / "sign-in.html"


class AuthEmailTemplateTests(unittest.TestCase):
    def test_sign_in_template_preserves_plain_six_digit_otp_flow(self):
        html = TEMPLATE.read_text(encoding="utf-8")
        rendered = html.replace("{{ .Token }}", "123456")

        self.assertEqual(html.count("{{ .Token }}"), 1)
        self.assertNotIn("{{ .ConfirmationURL }}", html)
        self.assertIn(">123456</td>", rendered)
        self.assertIn("six-digit code", rendered)
        self.assertIn("expires in 10 minutes", rendered)
        self.assertIn("safely ignore it", rendered)
        self.assertIn("support@meforash.com", rendered)
        self.assertNotIn("<img", html.lower())
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("https://", html.lower())


if __name__ == "__main__":
    unittest.main()
