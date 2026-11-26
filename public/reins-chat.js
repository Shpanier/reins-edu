// REINS Edu student chat: text with any Hebrew letter lays out right to left;
// text without (English, code) left to right.
// (CSS alone can only follow the first letter, and many Hebrew sentences here
// start with an English term: "Trivy סורק image…".)
(() => {
  const HE = /[֐-׿]/;
  // The student's choice of language: the EN/עב switch in the top bar
  // (addLangSwitch). It is kept in the browser and in a cookie that the chat's
  // server reads (student_app/app.py, _picked_lang). Chainlit's own labels
  // follow navigator.language, so that is set to the choice before Chainlit
  // starts: this file comes before Chainlit's script in the page, and runs first.
  const LANG_KEY = "reins_lang";
  const LANG_TAG = { he: "he-IL", en: "en-US" };
  const picked = (() => {
    let v = null;
    try { v = localStorage.getItem(LANG_KEY); } catch { /* storage blocked */ }
    if (!v) {
      const m = document.cookie.match(/(?:^|;\s*)reins_lang=(he|en)(?:;|$)/);
      v = m && m[1];
    }
    return v === "he" || v === "en" ? v : null;
  })();
  const savePicked = (lang) => {
    try { localStorage.setItem(LANG_KEY, lang); } catch { /* the cookie still has it */ }
    document.cookie = `${LANG_KEY}=${lang}; path=/; max-age=31536000; SameSite=Lax`;
  };
  if (picked) {
    savePicked(picked); // the cookie may have run out while the browser's copy hasn't
    const tag = LANG_TAG[picked];
    try {
      Object.defineProperty(navigator, "language", { configurable: true, get: () => tag });
      Object.defineProperty(navigator, "languages", { configurable: true, get: () => [tag] });
    } catch { /* the browser refuses: Chainlit's labels keep the browser's language */ }
    document.documentElement.lang = picked;
  }
  // This page's language: the student's choice, or else the browser's first
  // language (the one Chainlit's labels and the chat's server go by).
  const pageLang = () => picked || (/^he\b/i.test(navigator.language || "") ? "he" : "en");
  // Inside messages: paragraphs (Chainlit renders them as <div role="article">),
  // lists, headings, tables.
  const IN_MESSAGES = [
    '[role="article"]', "li", "ul", "ol", "h1", "h2", "h3", "h4", "blockquote", "table",
  ].map((s) => ".message-content " + s).join(", ");
  // Chainlit's own labels (sign-in page, buttons, dialogs, the exercise menu,
  // the line under the input): right to left only when they are in Hebrew.
  const LABELS = 'h1, h2, label, button, [role="option"], [role="dialog"] p, [role="alertdialog"] p, ' +
    '.watermark, form p';

  const mark = (el) => {
    const dir = HE.test(el.textContent || "") ? "rtl" : "ltr";
    if (el.getAttribute("dir") !== dir) el.setAttribute("dir", dir);
  };
  const markLabel = (el) => {
    if (el.closest(".message-content")) return;
    if (HE.test(el.textContent || "")) {
      if (el.getAttribute("dir") !== "rtl") el.setAttribute("dir", "rtl");
    } else if (el.getAttribute("dir") === "rtl") {
      el.removeAttribute("dir");
    }
  };
  // A text box follows what is typed in it; while empty, its placeholder.
  const markField = (el) => {
    if (el.type === "password") return;
    const dir = HE.test(el.value || el.placeholder || "") ? "rtl" : "ltr";
    if (el.dir !== dir) el.dir = dir;
  };
  // The sign-in page: what REINS stands for, under the heading (on a phone the
  // picture beside the form, which says it too, is hidden).
  const addAcronym = () => {
    if (!/\/login\/?$/.test(location.pathname)) return;
    const h = document.querySelector("form h1");
    if (!h || h.parentElement.querySelector(".reins-acronym")) return;
    const p = document.createElement("p");
    p.className = "reins-acronym";
    p.lang = "en";
    p.dir = "ltr";
    p.innerHTML = "<b>R</b>eviewed <b>E</b>xplanations, <b>I</b>nstructor-<b>N</b>avigated <b>S</b>teps";
    h.parentElement.appendChild(p);
  };
  // The sign-in page: Google and a code by email under the username and
  // password, when the lecturer turned them on (Settings; backend/signin.py).
  // The server answers with Chainlit's own sign-in cookie, so the chat opens
  // as if the student had typed a password.
  const SIGNIN_TEXT = {
    he: {
      or: "או", google: "כניסה עם Google", email: "כניסה עם קוד במייל",
      emailLabel: "כתובת המייל", send: "שליחת קוד",
      sent: "אם הכתובת {email} רשומה אצל המרצה, שלחנו אליה קוד בן 6 ספרות. הקוד תקף ל־{minutes} דקות.",
      spam: "לא הגיע תוך דקה? כדאי לבדוק בתיקיית הספאם.",
      codeLabel: "הקוד מהמייל", signIn: "כניסה", resend: "שליחת קוד חדש", back: "חזרה לשם משתמש וסיסמה",
      bad: "הקוד שגוי או שפג תוקפו.", tooMany: "התבקשו מכאן יותר מדי קודים. המתינו כמה דקות ונסו שוב.",
      notEmail: "זו לא כתובת מייל תקינה.", noServer: "השרת לא עונה. נסו שוב בעוד רגע.",
      errors: {
        unknown: "הכתובת {email} לא רשומה באף קורס. היכנסו עם שם המשתמש והסיסמה, או בקשו מהמרצה לרשום את הכתובת הזאת.",
        ambiguous: "לכתובת {email} יש יותר מחשבון אחד. היכנסו עם שם המשתמש והסיסמה.",
        blocked: "עם חשבון של מרצה נכנסים רק מהמחשב של המרצה.",
        expired: "הכניסה עם Google לקחה יותר מדי זמן, או שהתחילה בדפדפן אחר. נסו שוב.",
        cancelled: "הכניסה עם Google בוטלה.",
        google_error: "Google לא השלים את הכניסה. נסו שוב בעוד רגע.",
        unverified: "כתובת המייל של חשבון ה־Google הזה לא אומתה. היכנסו עם שם המשתמש והסיסמה.",
        off: "הכניסה עם Google לא פעילה כרגע. היכנסו עם שם המשתמש והסיסמה.",
        no_chat_page: "הצ'אט עוד לא מוכן לכניסה עם Google: המרצה צריך להפעיל מחדש את REINS Edu.",
      },
    },
    en: {
      or: "or", google: "Sign in with Google", email: "Sign in with a code by email",
      emailLabel: "Email address", send: "Send me a code",
      sent: "If {email} is on your lecturer's list, a 6-digit code is on its way to it. It works for {minutes} minutes.",
      spam: "Nothing after a minute? Look in your spam folder.",
      codeLabel: "The code from the email", signIn: "Sign in", resend: "Send a new code",
      back: "Back to username and password",
      bad: "Wrong or expired code.", tooMany: "Too many codes were asked for from here. Wait a few minutes and try again.",
      notEmail: "That isn't an email address.", noServer: "The server isn't answering. Try again in a moment.",
      errors: {
        unknown: "{email} isn't on any class list. Sign in with your username and password, or ask your lecturer to add this address.",
        ambiguous: "More than one account has the address {email}. Sign in with your username and password.",
        blocked: "A lecturer's account signs in only on the lecturer's computer.",
        expired: "Signing in with Google took too long, or started in another browser. Try again.",
        cancelled: "Signing in with Google was cancelled.",
        google_error: "Google didn't complete the sign-in. Try again in a moment.",
        unverified: "This Google account's email address isn't verified. Sign in with your username and password.",
        off: "Signing in with Google is off. Sign in with your username and password.",
        no_chat_page: "The chat isn't ready for Google sign-in yet: the lecturer needs to restart REINS Edu.",
      },
    },
  };
  const GOOGLE_G = '<svg viewBox="0 0 48 48" aria-hidden="true">' +
    '<path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>' +
    '<path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>' +
    '<path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>' +
    '<path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>';
  // What the server's sign-in offers, and the lecturer's language setting
  // (GET /api/login/methods), asked once for the page.
  let methodsAsked = null;
  const askMethods = () => methodsAsked || (methodsAsked = fetch("/api/login/methods")
    .then((r) => (r.ok ? r.json() : null)).catch(() => null));
  // null: not asked yet; false: the server offers neither (or is another program).
  let methods = null;
  // The lecturer's language setting: null until asked; "auto" when the server
  // doesn't say.
  let langSetting = null;
  const signin = { step: "buttons", email: "", minutes: 10, message: "", tone: "" };
  // Back from Google with ?signin_error=<why>&email=<address> (backend/routes/signin.py):
  // said in the box under the form, then removed from the address.
  const googleBack = (() => {
    const q = new URLSearchParams(location.search);
    const why = q.get("signin_error");
    if (!why) return null;
    const email = q.get("email") || "";
    q.delete("signin_error");
    q.delete("email");
    const rest = q.toString();
    history.replaceState(null, "", location.pathname + (rest ? "?" + rest : "") + location.hash);
    return { why, email };
  })();
  const onLogin = () => /\/login\/?$/.test(location.pathname);
  const chatBase = () => location.pathname.replace(/\/login\/?$/, "");
  const signinLang = () => {
    const forced = (methods && methods.chat_language) || langSetting;
    if (forced === "he" || forced === "en") return forced;
    return pageLang();
  };
  const fill = (s, v) => s.replace(/\{(\w+)\}/g, (_, k) => (k in v ? v[k] : ""));
  const el = (tag, attrs, children) => {
    const e = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "text") e.textContent = v;
      else if (k === "html") e.innerHTML = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v);
    });
    (children || []).forEach((c) => c && e.appendChild(c));
    return e;
  };
  const post = (path, body) => fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
    body: JSON.stringify(body),
  });

  const renderSignin = (box, form) => {
    const T = SIGNIN_TEXT[signinLang()];
    if (googleBack && !googleBack.shown) {
      googleBack.shown = true;
      signin.message = fill(T.errors[googleBack.why] || T.errors.google_error, { email: googleBack.email });
      signin.tone = "error";
    }
    box.dir = signinLang() === "he" ? "rtl" : "ltr";
    box.replaceChildren();
    form.style.display = signin.step === "buttons" ? "" : "none";
    const note = signin.message
      ? el("p", { class: "reins-signin__msg" + (signin.tone ? " is-" + signin.tone : ""), role: "status", text: signin.message })
      : null;
    if (signin.step === "buttons") {
      if (note) box.appendChild(note);
      box.appendChild(el("div", { class: "reins-signin__or" }, [el("span", { text: T.or })]));
      if (methods.google) {
        const a = el("a", {
          class: "reins-signin__btn", html: GOOGLE_G,
          href: "/api/login/google?to=chat",
        });
        a.appendChild(el("span", { text: T.google }));
        box.appendChild(a);
      }
      if (methods.email) {
        box.appendChild(el("button", {
          type: "button", class: "reins-signin__btn", text: T.email,
          onclick: () => { signin.step = "email"; signin.message = ""; signin.tone = ""; renderSignin(box, form); },
        }));
      }
      return;
    }
    const busy = (b) => box.querySelectorAll("button, input").forEach((x) => { x.disabled = b; });
    const sendCode = async () => {
      const input = box.querySelector("input[type=email]");
      signin.email = (input ? input.value : signin.email).trim();
      busy(true);
      try {
        const r = await post("/api/login/email", { email: signin.email, to: "chat", lang: signinLang() });
        if (r.ok) {
          signin.minutes = (await r.json()).minutes || 10;
          signin.step = "code";
          signin.message = fill(T.sent, { email: signin.email, minutes: signin.minutes });
          signin.tone = "";
        } else {
          signin.message = r.status === 429 ? T.tooMany : r.status === 422 ? T.notEmail : T.noServer;
          signin.tone = "error";
        }
      } catch {
        signin.message = T.noServer;
        signin.tone = "error";
      }
      renderSignin(box, form);
    };
    const checkCode = async () => {
      const code = (box.querySelector("input[name=code]").value || "").replace(/\D/g, "");
      busy(true);
      try {
        const r = await post("/api/login/email/verify", { email: signin.email, code, to: "chat" });
        if (r.ok) {
          location.href = chatBase() + "/";
          return;
        }
        signin.message = r.status === 401 ? T.bad : T.noServer;
      } catch {
        signin.message = T.noServer;
      }
      signin.tone = "error";
      renderSignin(box, form);
    };
    const back = el("button", {
      type: "button", class: "reins-signin__link", text: T.back,
      onclick: () => { signin.step = "buttons"; signin.message = ""; signin.tone = ""; renderSignin(box, form); },
    });
    if (signin.step === "email") {
      const input = el("input", { type: "email", dir: "ltr", autocomplete: "email", value: signin.email });
      box.appendChild(el("form", {
        class: "reins-signin__panel", novalidate: "",
        onsubmit: (e) => { e.preventDefault(); if (input.value.includes("@")) sendCode(); },
      }, [
        el("label", {}, [el("span", { text: T.emailLabel }), input]),
        note,
        el("button", { type: "submit", class: "reins-signin__primary", text: T.send }),
        back,
      ]));
      setTimeout(() => input.focus(), 0);
      return;
    }
    const codeInput = el("input", {
      name: "code", dir: "ltr", inputmode: "numeric", autocomplete: "one-time-code", maxlength: "6",
      oninput: (e) => { e.target.value = e.target.value.replace(/\D/g, "").slice(0, 6); },
    });
    box.appendChild(el("form", {
      class: "reins-signin__panel", novalidate: "",
      onsubmit: (e) => { e.preventDefault(); if (codeInput.value.length === 6) checkCode(); },
    }, [
      note,
      el("label", {}, [el("span", { text: T.codeLabel }), codeInput]),
      el("p", { class: "reins-signin__hint", text: T.spam }),
      el("button", { type: "submit", class: "reins-signin__primary", text: T.signIn }),
      el("div", { class: "reins-signin__row" }, [
        back,
        el("button", { type: "button", class: "reins-signin__link", text: T.resend, onclick: sendCode }),
      ]),
    ]));
    setTimeout(() => codeInput.focus(), 0);
  };

  const addSignin = () => {
    if (!onLogin()) return;
    if (methods === null) {
      methods = false;
      askMethods().then((m) => {
        methods = m && (m.google || m.email) && m.chat_page ? m : false;
        addSignin();
      });
      return;
    }
    if (!methods) return;
    // Chainlit's own form: the one with the password field.
    const pw = document.querySelector('form:not(.reins-signin__panel) input[type="password"]');
    const form = pw && pw.closest("form");
    if (!form) return;
    let box = document.querySelector(".reins-signin");
    if (box && box.previousElementSibling === form) return;
    if (box) box.remove();
    box = el("div", { class: "reins-signin" });
    form.insertAdjacentElement("afterend", box);
    renderSignin(box, form);
  };

  // The small logo of Azrieli College of Engineering Jerusalem, where REINS Edu
  // is made: an email link to its author (GET /api/contact; off hides it).
  // Under the REINS Edu logo of the sign-in page, and in the top bar of the chat.
  let contact = null; // null: not asked yet; false: no logo
  const collegeLink = (cls) => {
    const he = signinLang() === "he";
    const a = el("a", {
      class: "reins-college " + cls, href: "mailto:" + contact,
      title: (he ? "שליחת מייל: " : "Send an email: ") + contact,
    });
    a.appendChild(el("img", {
      src: "/public/azrieli.png", width: "160", height: "98",
      alt: he ? "המכללה האקדמית להנדסה עזריאלי ירושלים: שליחת מייל"
        : "Azrieli College of Engineering Jerusalem: send an email",
    }));
    return a;
  };
  const addCollege = () => {
    if (contact === null) {
      contact = false;
      fetch("/api/contact").then((r) => (r.ok ? r.json() : null)).then((d) => {
        contact = (d && d.email) || false;
        addCollege();
      }).catch(() => {});
      return;
    }
    if (!contact) return;
    if (onLogin()) {
      // Right under the REINS Edu logo at the top of the sign-in column.
      const logo = [...document.querySelectorAll("img")]
        .find((i) => /\/logo(\?|$)/.test(i.getAttribute("src") || "") && !i.closest("#header"));
      const row = logo && logo.parentElement;
      if (!row) return;
      const next = row.nextElementSibling;
      if (next && next.classList.contains("reins-college")) return;
      document.querySelectorAll(".reins-college--login").forEach((x) => x.remove());
      row.insertAdjacentElement("afterend", collegeLink("reins-college--login"));
      return;
    }
    const toggle = document.querySelector("#header #theme-toggle");
    if (!toggle || toggle.parentElement.querySelector(".reins-college")) return;
    const before = toggle.parentElement.querySelector(".reins-lang") || toggle;
    before.insertAdjacentElement("beforebegin", collegeLink("reins-college--header"));
  };

  // Before the language switch reloads the page: a student the chat signed in
  // itself (no sign-in page) would have to sign in again, since that sign-in
  // lives in this page's chat session. So the page asks the chat for a pass
  // (a window message, which Chainlit hands to the chat's server:
  // student_app/app.py, on_window_message) and keeps it in a cookie for the
  // next page, where the chat carries on in the same lab. No answer in time,
  // or an empty one (not signed in yet, or signed in on the sign-in page, which
  // a reload keeps), and the page just reloads.
  const PASS_COOKIE = "reins_resume";
  const keepSignin = () => new Promise((done) => {
    if (window.top !== window) { done(); return; }
    const id = Math.random().toString(36).slice(2);
    let timer = null;
    const onReply = (e) => {
      // Chainlit posts the chat's answer to this same window.
      if (e.source !== window || e.origin !== location.origin) return;
      const d = e.data;
      if (!d || d.reins !== "resume-pass-for" || d.id !== id) return;
      finish(d.pass);
    };
    const finish = (pass) => {
      clearTimeout(timer);
      window.removeEventListener("message", onReply);
      if (pass && /^[\w-]+$/.test(pass)) {
        document.cookie = `${PASS_COOKIE}=${pass}; path=/; max-age=60; SameSite=Strict`;
      }
      done();
    };
    timer = setTimeout(() => finish(""), 2500);
    window.addEventListener("message", onReply);
    window.postMessage({ reins: "resume-pass", id }, location.origin);
  });

  // The switch between English and Hebrew: in the chat's top bar beside the
  // light/dark button, and in a corner of the sign-in page. A click keeps the
  // choice and reloads the page, so that Chainlit's labels change with the
  // chat's own lines; the student stays signed in and the lab continues where
  // it was (keepSignin). Hidden when the lecturer fixed the chat's language.
  const LANG_NAMES = { en: ["EN", "English"], he: ["עב", "עברית"] };
  let switching = false; // a second click while the page asks for its pass does nothing
  const addLangSwitch = () => {
    if (langSetting === null) {
      langSetting = "auto";
      askMethods().then((m) => {
        langSetting = (m && m.chat_language) || "auto";
        if (langSetting !== "auto") document.querySelectorAll(".reins-lang").forEach((x) => x.remove());
        addLangSwitch();
      });
      return;
    }
    if (langSetting !== "auto") return;
    const login = onLogin();
    const toggle = login ? null : document.querySelector("#header #theme-toggle");
    const cls = "reins-lang " + (login ? "reins-lang--login" : "reins-lang--header");
    const old = document.querySelector(".reins-lang");
    if (old && old.className === cls && (login || old.nextElementSibling === toggle)) return;
    if (old) old.remove();
    if (!login && !toggle) return;
    const now = pageLang();
    const box = el("div", { class: cls, role: "group", "aria-label": now === "he" ? "שפה" : "Language" });
    ["en", "he"].forEach((lang) => {
      const [short, name] = LANG_NAMES[lang];
      box.appendChild(el("button", {
        type: "button", lang, dir: lang === "he" ? "rtl" : "ltr", title: name, "aria-label": name,
        "aria-pressed": String(lang === now), text: short,
        onclick: () => {
          if (lang === picked || switching) return;
          switching = true;
          savePicked(lang);
          keepSignin().then(() => location.reload());
        },
      }));
    });
    if (login) document.body.appendChild(box);
    else toggle.insertAdjacentElement("beforebegin", box);
  };

  const scan = () => {
    addAcronym();
    addSignin();
    addLangSwitch();
    addCollege();
    document.querySelectorAll(IN_MESSAGES).forEach(mark);
    document.querySelectorAll(LABELS).forEach(markLabel);
    document.querySelectorAll("input, textarea").forEach(markField);
  };

  // Messages arrive and stream in token by token: look again after changes.
  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    queued = true;
    setTimeout(() => { queued = false; scan(); }, 30);
  }).observe(document.body, { childList: true, subtree: true, characterData: true });

  document.addEventListener("input", (e) => {
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) markField(t);
  });

  // The "My work" button under the message box (a Chainlit command,
  // student_app/app.py; its names are chat_texts.py's cmd_my_work). Chainlit only
  // selects a command on a click and waits for Send; this one needs nothing
  // typed, so with the box empty a click sends it at once. (Runs before
  // Chainlit's own handler, so a button already selected is being unselected.)
  const MY_WORK = ["My work", "העבודה שלי"];
  document.addEventListener("click", (e) => {
    const btn = e.target instanceof Element ? e.target.closest("button.command-button") : null;
    if (!btn || !MY_WORK.some((name) => btn.id === "command-" + name)) return;
    if (btn.classList.contains("text-command")) return;
    const box = document.getElementById("chat-input");
    if (box && (box.value ?? box.textContent ?? "").trim()) return;
    setTimeout(() => { const send = document.getElementById("chat-submit"); if (send) send.click(); }, 80);
  }, true);
  scan();
})();
