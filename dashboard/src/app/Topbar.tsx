import { useEffect, useRef, useState } from "react";
import { BookOpen, ChevronDown, FileCheck2, LogOut, MonitorPlay, Settings as SettingsIcon, Share2, UserRound, Users, WifiOff } from "lucide-react";
import type { Settings } from "../api";
import { LanguageToggle, useLang } from "../i18n";
import { connection } from "../lib/connection";
import { Button } from "../components/ui";
import { Acronym, Brand } from "./FirstRun";
import { textDir } from "../lib/textDir";
import { CollegeLink } from "./CollegeLink";

export type Tab = "monitor" | "exercises" | "courses";

/** The red strip at the very top while the server isn't answering. */
export function ConnectionBanner() {
  const { t } = useLang();
  const [lost, setLost] = useState(connection.isLost());
  useEffect(() => connection.subscribe(setLost), []);
  if (!lost) return null;
  return <div className="vc-banner" role="alert"><WifiOff /> {t("connLost")}</div>;
}

function TutorStatus({ settings, onClick }: { settings: Settings | null; onClick: () => void }) {
  const { t } = useLang();
  if (!settings) return null;
  const { llm } = settings;
  const failing = llm.ready && llm.health.ok === false;
  const tone = !llm.ready ? "warning" : failing ? "danger" : "success";
  const label = !llm.ready ? t("statusNoKey") : failing ? t("statusError") : t("statusReady");
  return (
    <button type="button" className={`vc-status ${tone === "success" ? "" : `vc-status--${tone}`}`}
            title={failing ? llm.health.error : t("statusTitle")} onClick={onClick}>
      <span className={`vc-dot vc-dot--${tone}`} /> {label}
    </button>
  );
}

function AccountMenu({ settings, plugin, onSettings, onVerify, onSignOut }: {
  settings: Settings | null;
  plugin: boolean;
  onSettings: () => void;
  onVerify: () => void;
  onSignOut: () => void;
}) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  const pick = (fn: () => void) => () => { setOpen(false); fn(); };
  return (
    <div className="vc-menu" ref={box}>
      <Button variant="quiet" size="sm" icon={<UserRound />} aria-haspopup="menu" aria-expanded={open}
              aria-label={t("menuAccount")} onClick={() => setOpen((v) => !v)}>
        <ChevronDown />
      </Button>
      {open && (
        <div className="vc-menu__list" role="menu">
          {settings && (
            <div className="vc-menu__label">{t("menuSignedIn")}<strong dir={textDir(settings.user.name)}>{settings.user.name}</strong></div>
          )}
          <button role="menuitem" className="vc-menu__item" onClick={pick(onSettings)}><SettingsIcon /> {t("menuSettings")}</button>
          {plugin && <button role="menuitem" className="vc-menu__item" onClick={pick(onVerify)}><FileCheck2 /> {t("menuVerify")}</button>}
          <button role="menuitem" className="vc-menu__item" onClick={pick(onSignOut)}><LogOut /> {t("signOut")}</button>
        </div>
      )}
    </div>
  );
}

/** The side rail: the brand, the three pages (the live class counts what waits
 *  for the lecturer), and at the bottom the tutor's status, the bell, the
 *  language, the account and the one action every class starts with: sharing
 *  the students' link. Under 900px it is a bar across the top (shell.css). */
export function Rail({ tab, onTab, settings, plugin, bell, waiting, onShare, onSettings, onVerify, onSignOut }: {
  tab: Tab;
  onTab: (t: Tab) => void;
  settings: Settings | null;
  plugin: boolean;
  /** The notifications' bell (app/Notifications.tsx). */
  bell?: React.ReactNode;
  /** How many things wait for the lecturer in the live class (questions, steps, answers). */
  waiting: number;
  onShare: () => void;
  onSettings: () => void;
  onVerify: () => void;
  onSignOut: () => void;
}) {
  const { t } = useLang();
  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: "monitor", label: t("navClass"), icon: <MonitorPlay /> },
    { key: "exercises", label: t("navExercises"), icon: <BookOpen /> },
    { key: "courses", label: t("navCourses"), icon: <Users /> },
  ];
  return (
    <aside className="vc-rail">
      <div className="vc-rail__brand">
        <Brand />
        <CollegeLink className="vc-rail__college" />
        <Acronym />
      </div>
      <nav className="vc-nav" aria-label="REINS Edu">
        {tabs.map(({ key, label, icon }) => (
          <button key={key} type="button" className="vc-nav__item" aria-current={tab === key ? "page" : undefined}
                  onClick={() => onTab(key)}>
            {icon} {label}
            {key === "monitor" && waiting > 0 && (
              <span className="vc-nav__count" title={t("railWaiting", { n: waiting })}>
                {waiting > 99 ? "99+" : waiting}
                <span className="u-sr"> {t("railWaiting", { n: waiting })}</span>
              </span>
            )}
          </button>
        ))}
      </nav>
      <div className="vc-rail__foot">
        <div className="vc-rail__status"><TutorStatus settings={settings} onClick={onSettings} /></div>
        <div className="vc-rail__row">
          {bell}
          <LanguageToggle />
          <span className="u-push" />
          <AccountMenu settings={settings} plugin={plugin} onSettings={onSettings} onVerify={onVerify} onSignOut={onSignOut} />
        </div>
        <Button variant="attention" icon={<Share2 />} className="vc-rail__share" onClick={onShare}>{t("shareBtn")}</Button>
      </div>
    </aside>
  );
}
