export async function celebrate() {
  if (typeof window === "undefined" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const confetti = (await import("canvas-confetti")).default;
  const end = Date.now() + 700;
  const colors = ["#4f46e5", "#7c74ff", "#10b981", "#f59e0b", "#ec4899"];
  (function frame() {
    confetti({ particleCount: 5, angle: 60, spread: 60, origin: { x: 0, y: 0.75 }, colors });
    confetti({ particleCount: 5, angle: 120, spread: 60, origin: { x: 1, y: 0.75 }, colors });
    if (Date.now() < end) requestAnimationFrame(frame);
  })();
}
