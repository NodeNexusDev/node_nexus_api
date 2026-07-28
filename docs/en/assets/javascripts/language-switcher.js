document.addEventListener("DOMContentLoaded", () => {
  const match = window.location.pathname.match(/^(.*)\/(en|ru)(\/.*)?$/);
  if (!match) return;

  const [, prefix, , pagePath = "/"] = match;
  document.querySelectorAll("a[hreflang]").forEach((link) => {
    const locale = link.getAttribute("hreflang");
    if (locale === "en" || locale === "ru") {
      link.href = `${prefix}/${locale}${pagePath}`;
    }
  });
});
