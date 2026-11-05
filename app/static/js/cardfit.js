// Card helpers shared by the preview, the pass page and the print views.
//  - fitCards(): shrinks text that would overflow its fixed box, so long names
//    or addresses never push the layout around.
//  - zoomCards(): scales the mm-sized card to fill its container on screen.
(() => {
  const MIN = 0.5; // never shrink below 50% of the designed size

  function shrink(el, overflows) {
    el.style.fontSize = "";
    const base = parseFloat(getComputedStyle(el).fontSize);
    let size = base;
    while (overflows(el) && size > base * MIN) {
      size *= 0.95;
      el.style.fontSize = size + "px";
    }
  }

  function fitCards(root = document) {
    root.querySelectorAll(".bp-card .fit").forEach(el => shrink(el, e => e.scrollWidth > e.clientWidth + 0.5));
    root.querySelectorAll(".bp-card .fit-box").forEach(el => {
      // Boxes that align text with flexbox measure their inner span instead.
      const inner = el.querySelector(":scope > .fit-inner");
      shrink(el, inner
        ? e => inner.offsetHeight > e.clientHeight + 0.5 || inner.scrollWidth > e.clientWidth + 0.5
        : e => e.scrollHeight > e.clientHeight + 0.5 || e.scrollWidth > e.clientWidth + 0.5);
    });
  }

  function zoomCards(root = document) {
    root.querySelectorAll(".bp-zoom").forEach(box => {
      const card = box.querySelector(".bp-card");
      if (!card) return;
      card.style.zoom = "";
      const natural = card.offsetWidth;
      if (natural && box.clientWidth) card.style.zoom = (box.clientWidth / natural).toFixed(4);
    });
  }

  window.BuggyCard = { fitCards, zoomCards };
  const run = () => { zoomCards(); fitCards(); };
  document.addEventListener("DOMContentLoaded", run);
  window.addEventListener("load", run);           // after web fonts / images
  window.addEventListener("resize", () => zoomCards());
  window.addEventListener("beforeprint", () => {  // print at true size
    document.querySelectorAll(".bp-zoom .bp-card").forEach(c => (c.style.zoom = ""));
    fitCards();
  });
  window.addEventListener("afterprint", run);
})();
