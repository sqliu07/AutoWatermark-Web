document.addEventListener("DOMContentLoaded", async () => {
  const res = await fetch("/static/footer.html");
  const html = await res.text();

  document.body.insertAdjacentHTML("beforeend", html);

  const startYear = 2024;
  const currentYear = new Date().getFullYear();
  const el = document.getElementById("copyright");

  if (el) {
    el.textContent =
      startYear === currentYear
        ? startYear
        : `${startYear}–${currentYear}`;
  }
});
