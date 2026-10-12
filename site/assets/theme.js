(() => {
  const choices = ["system", "light", "dark"];
  const labels = { system: "System", light: "Light", dark: "Dark" };
  let theme = "system";
  try {
    const saved = localStorage.getItem("php-catalog-theme");
    if (choices.includes(saved)) theme = saved;
  } catch {
    // The system theme remains available when browser storage is restricted.
  }

  const applyTheme = () => {
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  };
  applyTheme();

  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.querySelector(".theme-toggle");
    if (!(toggle instanceof HTMLButtonElement)) return;
    const updateLabel = () => {
      const next = choices[(choices.indexOf(theme) + 1) % choices.length];
      toggle.textContent = `Theme: ${labels[theme]}`;
      toggle.setAttribute("aria-label", `Theme: ${labels[theme]}. Switch to ${labels[next].toLowerCase()} theme`);
    };
    toggle.hidden = false;
    updateLabel();
    toggle.addEventListener("click", () => {
      theme = choices[(choices.indexOf(theme) + 1) % choices.length];
      applyTheme();
      updateLabel();
      try {
        localStorage.setItem("php-catalog-theme", theme);
      } catch {
        // Changing the theme works without persisting the preference.
      }
    });
  });
})();
