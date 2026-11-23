import { useCallback, useEffect, useRef, useState } from "react";
import {
  auth, googleSigninUrl, login, loginMethods, requestEmailCode, tradeSigninTicket, verifyEmailCode,
  type LoginMethods, type LoginResult,
} from "../api";
import { LanguageToggle, useLang, type StringKey } from "../i18n";
import { describeError } from "../lib/errors";
import { Button, Field, Notice } from "./ui";
import { Acronym, Brand } from "../app/FirstRun";
import { CollegeLink } from "../app/CollegeLink";

interface Props {
  onLoggedIn: () => void;
}

// Dev-mode auto-login, mirroring the student app's DEV_AUTO_LOGIN_CODE. Set
// VITE_DEV_AUTO_LOGIN_CODE to a teacher code in dashboard/.env.local and the
// gate signs in automatically, once. Only ever honored when Vite runs in dev
// mode (import.meta.env.DEV); production builds compile this down to "".
const DEV_CODE = import.meta.env.DEV
  ? ((import.meta.env.VITE_DEV_AUTO_LOGIN_CODE as string) || "").trim().toUpperCase()
  : "";
// "Sign out" must stay signed out: the automatic sign-in happens once per page load.
let devAutoTried = false;

/** What the address says after a Google sign-in: ?signin=<ticket> or
 *  ?signin_error=<why> (backend/routes/signin.py). Read once, then removed
 *  from the address so a reload doesn't repeat it. */
export function takeSigninReturn(): { ticket: string | null; error: string | null } {
  const q = new URLSearchParams(window.location.search);
  const ticket = q.get("signin");
  const error = q.get("signin_error");
  if (ticket !== null || error !== null) {
    q.delete("signin");
    q.delete("signin_error");
    const rest = q.toString();
    window.history.replaceState(null, "", window.location.pathname + (rest ? `?${rest}` : "") + window.location.hash);
  }
  return { ticket, error };
}

/** Back from Google with a ticket: the sign-in screen takes it, even when this
 *  browser still holds an older sign-in. */
export function hasSigninReturn(): boolean {
  return new URLSearchParams(window.location.search).has("signin");
}

const GOOGLE_ERRORS: Record<string, StringKey> = {
  unknown: "loginGoogleUnknown",
  student: "loginNotTeacher",
  ambiguous: "loginGoogleAmbiguous",
  blocked: "loginBlocked",
  expired: "loginGoogleExpired",
  cancelled: "loginGoogleCancelled",
  google_error: "loginGoogleFailed",
  unverified: "loginGoogleUnverified",
  off: "loginGoogleOff",
};

type Mode = "password" | "email" | "code";

/** Google's "G", as its sign-in buttons show it. */
function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

// The dashboard is behind a lecturer's sign-in. A student's username is refused
// here even though it authenticates: every dashboard endpoint needs a lecturer.
// Besides the username and password: Google, or a code sent by email, when the
// lecturer turned them on (Settings, backend/signin.py).
export function LoginGate({ onLoggedIn }: Props) {
  const { t, lang } = useLang();
  const [code, setCode] = useState(devAutoTried ? "" : DEV_CODE);
  // Until a password is set, it is the username itself (backend/passwords.py).
  const [password, setPassword] = useState(devAutoTried ? "" : DEV_CODE);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [methods, setMethods] = useState<LoginMethods | null>(null);
  const [mode, setMode] = useState<Mode>("password");
  const [email, setEmail] = useState("");
  const [emailCode, setEmailCode] = useState("");
  const [sentNote, setSentNote] = useState<string | null>(null);

  const finish = useCallback((res: LoginResult) => {
    if (res.role !== "teacher") {
      setError(t("loginNotTeacher"));
      return;
    }
    auth.set(res.token);
    onLoggedIn();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onLoggedIn]);

  const attempt = useCallback(
    async (raw: string, pass: string) => {
      setError(null);
      setBusy(true);
      try {
        finish(await login(raw.trim().toUpperCase(), pass));
      } catch (err) {
        setError(err instanceof Error && err.message === "bad-code" ? t("loginBad") : describeError(err, t));
      } finally {
        setBusy(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [finish],
  );

  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    loginMethods().then(setMethods);
    // Back from Google: trade the ticket for a sign-in, or say why it failed.
    const back = takeSigninReturn();
    if (back.error) setError(t(GOOGLE_ERRORS[back.error] ?? "loginGoogleFailed"));
    if (back.ticket) {
      setBusy(true);
      tradeSigninTicket(back.ticket)
        .then(finish)
        .catch((err) => setError(err instanceof Error && err.message === "bad-code"
          ? t("loginTicketExpired") : describeError(err, t)))
        .finally(() => setBusy(false));
      return;
    }
    if (DEV_CODE && !devAutoTried) {
      devAutoTried = true;
      attempt(DEV_CODE, DEV_CODE);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sendCode = async () => {
    setError(null);
    setBusy(true);
    try {
      const r = await requestEmailCode(email.trim(), lang);
      setSentNote(t("loginCodeSent", { email: email.trim(), minutes: String(r.minutes) }));
      setEmailCode("");
      setMode("code");
    } catch (err) {
      setError(err instanceof Error && err.message === "too-many" ? t("loginTooManyCodes") : describeError(err, t));
    } finally {
      setBusy(false);
    }
  };

  const checkCode = async () => {
    setError(null);
    setBusy(true);
    try {
      finish(await verifyEmailCode(email.trim(), emailCode));
    } catch (err) {
      setError(err instanceof Error && err.message === "bad-code" ? t("loginCodeBad") : describeError(err, t));
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "password") attempt(code, password);
    else if (mode === "email") sendCode();
    else checkCode();
  };

  const back = () => { setMode("password"); setError(null); setSentNote(null); };
  const others = !!methods && (methods.google || methods.email);

  return (
    <div className="vc-auth">
      <form className="vc-auth__card" onSubmit={submit}>
        <div className="vc-auth__top"><Brand /><LanguageToggle /></div>
        <Acronym line />
        <h1 className="vc-auth__title">{t("loginTitle")}</h1>
        <p className="vc-auth__lead">{t("loginLead")}</p>

        {mode === "password" && others && (
          <div className="vc-auth__alt">
            {methods?.google && (
              <a className="vc-btn vc-auth__google" href={googleSigninUrl()}>
                <GoogleMark />{t("loginWithGoogle")}
              </a>
            )}
            {methods?.email && (
              <Button size="lg" block onClick={() => { setMode("email"); setError(null); }}>
                {t("loginWithEmail")}
              </Button>
            )}
            <div className="vc-auth__or"><span>{t("loginOr")}</span></div>
          </div>
        )}

        {mode === "password" && (
          <>
            <Field label={t("loginUser")} value={code} onChange={setCode} autoFocus={!others} autoComplete="username" />
            <Field label={t("loginPass")} value={password} onChange={setPassword} type="password"
                   autoComplete="current-password" />
          </>
        )}
        {mode === "email" && (
          <Field label={t("loginEmail")} value={email} onChange={setEmail} type="email" autoFocus
                 autoComplete="email" />
        )}
        {mode === "code" && (
          <>
            {sentNote && <Notice tone="info" className="u-mb-12">{sentNote}</Notice>}
            <Field label={t("loginCode")} value={emailCode}
                   onChange={(v) => setEmailCode(v.replace(/\D/g, "").slice(0, 6))}
                   autoFocus autoComplete="one-time-code" hint={t("loginNoMail")} />
          </>
        )}

        {DEV_CODE && busy && <Notice tone="warning" className="u-mb-12">Dev mode: signing in as <code>{DEV_CODE}</code>…</Notice>}
        {error && <Notice tone="danger" className="u-mb-12">{error}</Notice>}

        {mode === "password" && (
          <Button variant="primary" size="lg" block type="submit" disabled={!code.trim() || !password} busy={busy}>
            {t("loginBtn")}
          </Button>
        )}
        {mode === "email" && (
          <Button variant="primary" size="lg" block type="submit" disabled={!email.includes("@")} busy={busy}>
            {t("loginSendCode")}
          </Button>
        )}
        {mode === "code" && (
          <Button variant="primary" size="lg" block type="submit" disabled={emailCode.length !== 6} busy={busy}>
            {t("loginBtn")}
          </Button>
        )}
        {mode !== "password" && (
          <div className="u-row u-between u-mt-12">
            <Button variant="link" onClick={back}>{t("loginBack")}</Button>
            {mode === "code" && <Button variant="link" onClick={sendCode} disabled={busy}>{t("loginResend")}</Button>}
          </div>
        )}
        <p className="vc-auth__foot">{t("loginFoot")}</p>
        <div className="vc-auth__college"><CollegeLink /></div>
      </form>
    </div>
  );
}
