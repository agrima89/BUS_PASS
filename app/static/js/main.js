// Sidebar toggle (mobile), flash dismissal, and delete confirmation.
document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.getElementById("sidebar");
  document.getElementById("menuBtn")?.addEventListener("click", () => sidebar.classList.toggle("open"));

  document.querySelectorAll(".flash-x").forEach(b =>
    b.addEventListener("click", () => b.parentElement.remove()));

  document.querySelectorAll("form[data-confirm]").forEach(f =>
    f.addEventListener("submit", e => { if (!confirm(f.dataset.confirm)) e.preventDefault(); }));
});
