# Sign-in email and iPhone code entry

September 12, 2026. The reviewed Supabase Magic Link and Confirm Signup template is [`web/email/sign-in.html`](../web/email/sign-in.html). It presents one plain, contiguous six-digit `{{ .Token }}` value, states the ten-minute lifetime, and includes an unrequested-email notice and support address. It uses a lightweight presentation table with inline styles in the Meforash ivory, sage, and ink palette. The message has no image, remote font, script, tracking pixel, or external stylesheet dependency.

The template is a deployment input, not a browser asset. It is deliberately absent from the beta server's static allowlist. Copying it to the provider does not happen automatically from this repository.

## Provider configuration

In the hosted Supabase project, open **Authentication → Email Templates → Magic Link**, set the subject to `Your meforash sign-in code`, and paste the template HTML. Apply the same subject and HTML to **Confirm Signup** for new users. The template includes `{{ .Token }}` and omits `{{ .ConfirmationURL }}` so `signInWithOtp` sends a code rather than a magic link. In **Authentication → Sign In / Providers → Email**, set **Email OTP length** to `6` and **Email OTP expiration** to `600` seconds.

Apply the template, length, and expiry together. Until all three values are live, the message or page could promise a format or lifetime that the provider does not enforce. Send a fresh code after the change; an earlier code is not a valid check of the new settings. Confirm the received message has six adjacent ASCII digits, says ten minutes, has no broken remote content, and signs in successfully before treating the rollout as complete.

Supabase documents that `{{ .Token }}` is the email OTP variable and that email OTP length and expiry are configurable. Its documented defaults are six digits and one hour, so the ten-minute statement depends on the project-specific `600`-second setting. Supabase also warns that link prefetching can consume magic links; a typed OTP avoids that link-prefetch path. See [passwordless email sign-in](https://supabase.com/docs/guides/auth/auth-email-passwordless), [email templates](https://supabase.com/docs/guides/auth/auth-email-templates), and [CLI configuration fields](https://supabase.com/docs/guides/local-development/cli/config#auth-email-otp-expiry).

## iPhone behavior

The page retains a single text input with `inputmode="numeric"`, `pattern="[0-9]{6}"`, `maxlength="6"`, and `autocomplete="one-time-code"`. Apple explicitly identifies `autocomplete="one-time-code"` as the web-field signal for verification-code AutoFill. The numeric input mode asks for a suitable keyboard without the leading-zero and value-format behavior of `type="number"`. See [Apple's Password AutoFill guidance](https://developer.apple.com/documentation/security/enabling-password-autofill-on-an-html-input-element) and [verification-code guidance](https://developer.apple.com/documentation/authenticationservices/securing-logins-with-icloud-keychain-verification-codes).

The Apple guidance cited here does not specify an email-body grammar comparable to its domain-bound SMS format. The email therefore makes the code easy to detect without claiming guaranteed Mail extraction: the six digits remain adjacent in one text node, are visually prominent, and are not split into separate cells or characters. The page tells iPhone readers that the suggestion *may* appear above the keyboard.

Filling or typing all six digits does not submit the form. The reader still activates **Verify code**, preserving a chance to inspect or correct the code and avoiding an authentication request triggered solely by AutoFill. Browser tests cover the exact six-digit check, the iPhone autocomplete attributes, no submission on input, invalid-code recovery, and preservation of the current conversation and draft through sign-in.

## Hosted configuration check

Both Magic Link and Confirm Signup templates and subjects were applied through the authenticated Supabase Management API and re-read byte-for-byte. Existing six-digit, 600-second expiry settings, custom Resend SMTP, and canonical site/redirect URLs were verified. This configuration check does not prove inbox placement or physical-device autofill. Request a fresh code in the browser where it will be entered; Meforash also requires that browser’s authentication-challenge cookie.
