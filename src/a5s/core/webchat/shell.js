"use strict";
// Every page's frame: a sidebar of the pages the signed-in person may use, and who they are,
// as a5s works them out (/shell/api), which names each page, its icon, its heading and its
// address, for the studio's sidebar and palette too (core/shell_api.py). Each page still checks
// for itself who may use it: the sidebar only leaves out those that would refuse them. Built
// from elements and text alone, as every page is: no markup from anywhere else.

(() => {
  // Icons, as lines on a 24-unit square
  const ICONS = {
    chat: ["M4 5.5h16v10.5H9l-5 4z"],
    tasks: ["M10 6.5h10", "M10 12h10", "M10 17.5h10", "M4 6.5l1.5 1.5 2.5-2.5", "M4 12l1.5 1.5 2.5-2.5",
            "M4 17.5l1.5 1.5 2.5-2.5"],
    book: ["M5 4.5h10.5a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3z", "M5 17a3 3 0 0 1 3-3h10.5"],
    studio: ["M3.5 6.5h5v5h-5z", "M15.5 3.5h5v5h-5z", "M15.5 15.5h5v5h-5z", "M8.5 9h3.5v-3h3.5",
             "M12 9v9h3.5"],
    map: ["M12 2.8a2.2 2.2 0 1 0 0 4.4 2.2 2.2 0 0 0 0-4.4z", "M6 16.8a2.2 2.2 0 1 0 0 4.4 2.2 2.2 0 0 0 0-4.4z",
          "M18 16.8a2.2 2.2 0 1 0 0 4.4 2.2 2.2 0 0 0 0-4.4z", "M12 7.2v4.3", "M6 16.8v-5.3h12v5.3"],
    decide: ["M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17z", "M8 12.2l2.7 2.7L16.2 9.4"],
    grade: ["M12 3.8l2.5 5.1 5.6.8-4 4 .9 5.6-5-2.7-5 2.7.9-5.6-4-4 5.6-.8z"],
    settings: ["M4 7h9", "M17 7h3", "M4 17h3", "M11 17h9", "M15 4.5v5", "M9 14.5v5"],
    audit: ["M12 3l7.5 3v6c0 4.5-3.2 7.8-7.5 9-4.3-1.2-7.5-4.5-7.5-9V6z", "M9 12l2.2 2.2L15.5 10"],
    admin: ["M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z", "M3 20a6 6 0 0 1 12 0",
            "M16.5 4.3a3.5 3.5 0 0 1 0 6.4", "M18.5 14.5a6 6 0 0 1 2.5 5.5"],
    spend: ["M6 3.5h12v17l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3z", "M9 8h6", "M9 11.5h6", "M9 15h3"],  // as Ocean's icons/
    officer: ["M6 10.5h12v9.5H6z", "M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3", "M12 14.5v2"],
    attach: ["M19.5 11.5l-7.8 7.8a5 5 0 0 1-7.1-7.1l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7l-8.4 8.4a1.6 1.6 0 0 1-2.3-2.3l7.6-7.6"],
    // an agent's mark, as the studio draws it (docs/design.md)
    agent: ["M7 8.5h10a2.5 2.5 0 0 1 2.5 2.5v6A2.5 2.5 0 0 1 17 19.5H7A2.5 2.5 0 0 1 4.5 17v-6A2.5 2.5 0 0 1 7 8.5z",
            "M12 4.5v4", "M9.5 13.5h.01", "M14.5 13.5h.01", "M9.5 16.5h5"],
  };
  const NS = "http://www.w3.org/2000/svg";
  const here = location.pathname.split("/")[1] || "chat";

  function icon(name) {
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "icon");
    for (const line of ICONS[name] || []) {
      const path = document.createElementNS(NS, "path");
      path.setAttribute("d", line);
      svg.append(path);
    }
    return svg;
  }

  function element(tag, text, className) {
    const found = document.createElement(tag);
    if (text !== undefined && text !== null) found.textContent = String(text);
    if (className) found.className = className;
    return found;
  }

  function initials(name) {
    return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
  }

  function frame() {  // the page's own elements, moved beside a sidebar
    if (document.body.classList.contains("app")) return;
    const side = element("aside", null, "sidebar");
    const brand = element("a", null, "brand");
    brand.href = "/chat/";
    brand.append(element("span", "a5", "mark"), element("span", "a5s"));
    const nav = element("nav");
    nav.id = "pages";
    nav.setAttribute("aria-label", "a5s's pages");
    const me = element("div", null, "me");
    me.id = "me";
    side.append(brand, nav, me);
    const page = element("div", null, "page");
    while (document.body.firstChild) page.append(document.body.firstChild);
    document.body.append(side, page);
    document.body.classList.add("app");
  }

  function pages(allowed, you) {  // in the order a5s gives them, each under its heading
    const nav = document.getElementById("pages");
    nav.replaceChildren();
    let heading = null;
    for (const place of allowed) {
      if (place.group !== heading) {
        heading = place.group;
        nav.append(element("div", heading, "group"));
      }
      const link = element("a");
      link.href = place.at;
      link.append(icon(place.icon), element("span", place.name));
      if (place.page === here) link.setAttribute("aria-current", "page");
      nav.append(link);
    }
    const me = document.getElementById("me");
    me.replaceChildren();
    if (you) me.append(element("span", initials(you), "avatar"), element("span", you));
  }

  window.a5s = {
    // Called by each page once it has signed someone in, with their sign-in: the language they
    // read, as /shell/api says, for the page to speak, or English
    async signedIn(token) {
      try {
        const answer = await fetch("/shell/api", { headers: { Authorization: `Bearer ${token}` } });
        if (!answer.ok) return "en";  // the page says what's wrong, as it always did
        const found = await answer.json();
        pages(found.pages, found.you);
        if (found.language === "th") document.getElementById("pages").setAttribute("aria-label", "หน้าต่างๆ ของ a5s");
        return found.language || "en";
      } catch {
        return "en";  // the sidebar is a convenience: the page works without it
      }
    },
    icon,
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", frame);
  else frame();
})();
