import { useEffect, useState } from "react";
import { api, type SigninSave, type SigninSettings as Status } from "../api";
import { useLang } from "../i18n";
import { describeError } from "../lib/errors";
import { Button, CopyButton, FormField, Input, Loading, Notice, Select, Switch, useToast } from "../components/ui";

/** Settings → signing in without a password: the lecturer's own address, the
 *  mail server that sends the codes, and the Google client (backend/signin.py).
 *  Passwords and secrets are never shown again: an empty field keeps them. */
export function SigninSettings() {
  const { t, lang } = useLang();
  const toast = useToast();
  const [s, setS] = useState<Status | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  const [myEmail, setMyEmail] = useState("");
  const [mail, setMail] = useState({ host: "", port: "587", user: "", password: "", sender: "", security: "starttls" });
  const [google, setGoogle] = useState({ id: "", secret: "" });

  const load = (next: Status) => {
    setS(next);
    setMyEmail(next.my_email);
    setMail({ host: next.email.host, port: String(next.email.port), user: next.email.user, password: "",
              sender: next.email.sender === next.email.user ? "" : next.email.sender, security: next.email.security });
    setGoogle({ id: next.google.client_id, secret: "" });
  };

  useEffect(() => {
    api.signinSettings().then(load).catch((e) => setLoadError(describeError(e, t)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async (what: string, body: SigninSave) => {
    setBusy(what);
    setTestResult(null);
    try {
      load(await api.saveSignin(body));
      toast.success(t("setSaved"));
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(null);
    }
  };

  const saveMine = async () => {
    setBusy("mine");
    try {
      const r = await api.saveMyEmail(myEmail.trim());
      setMyEmail(r.my_email);
      setS((prev) => (prev ? { ...prev, my_email: r.my_email } : prev));
      toast.success(t("setSaved"));
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(null);
    }
  };

  const test = async () => {
    setBusy("test");
    setTestResult(null);
    try {
      setTestResult(await api.testEmail(lang));
    } catch (e) {
      setTestResult({ ok: false, message: describeError(e, t) });
    } finally {
      setBusy(null);
    }
  };

  if (loadError) return <Notice tone="danger">{loadError}</Notice>;
  if (!s) return <Loading />;

  const state = (m: { on: boolean; ready: boolean }) => (m.on ? t("siOn") : m.ready ? t("siOff") : t("siNotSet"));
  const mailBody = (): SigninSave => ({
    smtp_host: mail.host.trim(), smtp_port: Number(mail.port) || 587, smtp_user: mail.user.trim(),
    smtp_password: mail.password || undefined, smtp_from: mail.sender.trim(),
    smtp_security: mail.security as SigninSave["smtp_security"],
  });

  return (
    <div className="vc-signin-settings">
      <h3 className="u-mb-8">{t("siTitle")}</h3>
      <p className="vc-hint u-mb-12">{t("siLead")}</p>
      {s.restart_needed && <Notice tone="warning" className="u-mb-12">{t("siRestart")}</Notice>}
      <p className="u-sm u-mb-4">{t("siStudents", { n: s.students.with_email, total: s.students.total })}</p>
      {s.students.with_email < s.students.total && <p className="vc-hint u-mb-12">{t("siStudentsHint")}</p>}

      <form className="u-row u-row--top u-wrap u-mb-16" onSubmit={(e) => { e.preventDefault(); saveMine(); }}>
        <FormField label={t("siMyEmail")} hint={t("siMyEmailHint")} className="u-grow">
          <Input type="email" dir="ltr" value={myEmail} autoComplete="email" onChange={(e) => setMyEmail(e.target.value)} />
        </FormField>
        <Button type="submit" className="vc-signin-settings__inline" busy={busy === "mine"}
                disabled={busy !== null || myEmail.trim() === s.my_email}>{t("siSave")}</Button>
      </form>

      <fieldset className="vc-signin-settings__box">
        <legend className="u-row u-gap-8">
          <span className="u-bold">{t("siEmailTitle")}</span>
          <span className={`vc-signin-settings__state${s.email.on ? " is-on" : ""}`}>{state(s.email)}</span>
        </legend>
        <form onSubmit={(e) => { e.preventDefault(); save("mail", mailBody()); }}>
          <div className="vc-signin-settings__grid">
            <FormField label={t("siHost")}>
              <Input dir="ltr" value={mail.host} placeholder="smtp.gmail.com" spellCheck={false}
                     onChange={(e) => setMail({ ...mail, host: e.target.value })} />
            </FormField>
            <FormField label={t("siPort")}>
              <Input dir="ltr" inputMode="numeric" value={mail.port}
                     onChange={(e) => setMail({ ...mail, port: e.target.value.replace(/\D/g, "") })} />
            </FormField>
            <FormField label={t("siSecurity")}>
              <Select value={mail.security} onChange={(e) => setMail({ ...mail, security: e.target.value })}>
                <option value="starttls">STARTTLS</option>
                <option value="ssl">SSL/TLS</option>
                <option value="none">{t("siSecurityNone")}</option>
              </Select>
            </FormField>
            <FormField label={t("siUser")}>
              <Input dir="ltr" value={mail.user} autoComplete="off" spellCheck={false}
                     onChange={(e) => setMail({ ...mail, user: e.target.value })} />
            </FormField>
            <FormField label={t("siPassword")} hint={s.email.password_set ? t("siPasswordKeep") : undefined}
                       className="vc-signin-settings__span2">
              <Input type="password" dir="ltr" value={mail.password} autoComplete="new-password"
                     placeholder={s.email.password_set ? "••••••••" : ""}
                     onChange={(e) => setMail({ ...mail, password: e.target.value })} />
            </FormField>
            <FormField label={t("siSender")} hint={t("siSenderHint")} className="vc-signin-settings__span2">
              <Input type="email" dir="ltr" value={mail.sender} spellCheck={false}
                     onChange={(e) => setMail({ ...mail, sender: e.target.value })} />
            </FormField>
          </div>
          <p className="vc-hint u-mb-12">{t("siGmailHint")}</p>
          {testResult && <Notice tone={testResult.ok ? "success" : "danger"} className="u-mb-12">{testResult.message}</Notice>}
          <div className="u-row u-wrap">
            <Button variant="primary" type="submit" busy={busy === "mail"} disabled={busy !== null}>{t("siSave")}</Button>
            <Button onClick={test} busy={busy === "test"} disabled={busy !== null || !s.email.ready || !s.my_email}
                    title={!s.my_email ? t("siTestNeedsEmail") : undefined}>{t("siTest")}</Button>
            <span className="u-push" />
            <Switch checked={s.email.switch} disabled={busy !== null || !s.email.ready} label={t("siEmailTitle")}
                    onChange={(v) => save("mail-on", { email_on: v })}>{s.email.switch ? t("siOn") : t("siOff")}</Switch>
          </div>
        </form>
      </fieldset>

      <fieldset className="vc-signin-settings__box">
        <legend className="u-row u-gap-8">
          <span className="u-bold">{t("siGoogleTitle")}</span>
          <span className={`vc-signin-settings__state${s.google.on ? " is-on" : ""}`}>{state(s.google)}</span>
        </legend>
        <form onSubmit={(e) => {
          e.preventDefault();
          save("google", { google_client_id: google.id.trim(), google_client_secret: google.secret.trim() || undefined });
        }}>
          <p className="vc-hint u-mb-8">{t("siGoogleHint")}</p>
          <ul className="vc-signin-settings__urls u-mb-12">
            {s.google.callback_urls.map((u) => (
              <li key={u} className="u-row">
                <code dir="ltr" className="u-grow u-truncate">{u}</code>
                <CopyButton text={u} size="sm" />
              </li>
            ))}
          </ul>
          <div className="vc-signin-settings__grid vc-signin-settings__grid--two">
            <FormField label={t("siClientId")}>
              <Input dir="ltr" mono value={google.id} spellCheck={false} placeholder="….apps.googleusercontent.com"
                     onChange={(e) => setGoogle({ ...google, id: e.target.value })} />
            </FormField>
            <FormField label={t("siClientSecret")} hint={s.google.secret_set ? t("siPasswordKeep") : undefined}>
              <Input type="password" dir="ltr" mono value={google.secret} autoComplete="new-password"
                     placeholder={s.google.secret_set ? "••••••••" : ""}
                     onChange={(e) => setGoogle({ ...google, secret: e.target.value })} />
            </FormField>
          </div>
          <div className="u-row u-wrap">
            <Button variant="primary" type="submit" busy={busy === "google"} disabled={busy !== null}>{t("siSave")}</Button>
            <span className="u-push" />
            <Switch checked={s.google.switch} disabled={busy !== null || !s.google.ready} label={t("siGoogleTitle")}
                    onChange={(v) => save("google-on", { google_on: v })}>{s.google.switch ? t("siOn") : t("siOff")}</Switch>
          </div>
        </form>
      </fieldset>
    </div>
  );
}
