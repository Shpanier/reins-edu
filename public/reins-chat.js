// REINS Edu student chat: text with any Hebrew letter lays out right to left;
// text without (English, code) left to right.
// (CSS alone can only follow the first letter, and many Hebrew sentences here
// start with an English term: "Trivy סורק image…".)
(() => {
  const HE = /[֐-׿]/;
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
  const scan = () => {
    addAcronym();
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
  scan();
})();
