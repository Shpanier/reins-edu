import { useEffect, useState } from "react";
import { useLang } from "../i18n";

// Asked once per page: the address behind the logo (GET /api/contact, public;
// REINS_CONTACT_EMAIL=off hides the logo).
let contact: Promise<string | null> | null = null;
function contactEmail(): Promise<string | null> {
  contact ??= fetch("/api/contact")
    .then((r) => (r.ok ? r.json() : { email: null }))
    .then((d: { email?: string | null }) => d.email ?? null)
    .catch(() => null);
  return contact;
}

/** The small logo of Azrieli College of Engineering Jerusalem, where REINS Edu
 *  is made: an email link to its author, as on the project page. */
export function CollegeLink({ className }: { className?: string }) {
  const { t } = useLang();
  const [email, setEmail] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    contactEmail().then((e) => { if (live) setEmail(e); });
    return () => { live = false; };
  }, []);
  if (!email) return null;
  return (
    <a className={"vc-college" + (className ? ` ${className}` : "")} href={`mailto:${email}`}
       title={t("collegeTitle", { email })}>
      <img src="/azrieli.png" width={160} height={98} alt={t("collegeAlt")} />
    </a>
  );
}
