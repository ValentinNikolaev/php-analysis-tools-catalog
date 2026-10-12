(() => {
  document.documentElement.classList.add("js");
  const menu = document.querySelector(".site-nav__disclosure");
  if (!(menu instanceof HTMLDetailsElement)) return;
  const mobile = window.matchMedia("(max-width: 720px)");
  const updateMenu = () => { menu.open = !mobile.matches; };
  updateMenu();
  mobile.addEventListener("change", updateMenu);
  menu.addEventListener("click", (event) => {
    if (mobile.matches && event.target instanceof Element && event.target.closest("a")) {
      menu.open = false;
    }
  });
  menu.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && mobile.matches) {
      menu.open = false;
      menu.querySelector("summary")?.focus();
    }
  });
})();
