// Small progressive enhancements: card reveal, keyboard shortcuts, drill timer.
(function () {
  const typing = () => ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) &&
    document.activeElement.type !== "radio" && document.activeElement.type !== "checkbox";

  // Flash cards
  const reveal = document.getElementById("reveal");
  const rate = document.getElementById("rate");
  const back = document.querySelector(".flash-back");
  function show() {
    if (!back || !back.hidden) return;
    back.hidden = false;
    rate.hidden = false;
    reveal.hidden = true;
  }
  if (reveal) {
    reveal.addEventListener("click", show);
    document.getElementById("flash").addEventListener("click", show);
  }

  // Drill timer
  const timer = document.getElementById("timer");
  if (timer) {
    const start = Date.parse(timer.dataset.start);
    const tick = () => {
      const s = Math.max(0, (Date.now() - start) / 1000);
      timer.textContent = s.toFixed(1) + "s";
      timer.style.color = s > 30 ? "var(--bad)" : "";
    };
    tick();
    setInterval(tick, 100);
  }

  // Keyboard shortcuts
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (reveal) {
      if (e.code === "Space" && !typing()) { e.preventDefault(); show(); return; }
      if (!rate.hidden && ["1", "2", "3", "4"].includes(e.key)) {
        rate.querySelector(`button[value="${e.key}"]`).click();
        return;
      }
    }
    const next = document.getElementById("next");
    if (next && e.key === "Enter" && !typing()) { e.preventDefault(); next.click(); return; }
    // Pick answer options with A-H (or 1-8) on question pages.
    const opts = document.querySelectorAll(".options input:not([disabled])");
    if (opts.length && !typing()) {
      let i = "abcdefgh".indexOf(e.key.toLowerCase());
      if (i < 0 && /^[1-8]$/.test(e.key)) i = Number(e.key) - 1;
      if (i >= 0 && i < opts.length) {
        const o = opts[i];
        o.checked = o.type === "checkbox" ? !o.checked : true;
        e.preventDefault();
      } else if (e.key === "Enter") {
        const form = opts[0].form;
        if ([...opts].some((o) => o.checked)) form.requestSubmit();
      }
    }
  });
})();
