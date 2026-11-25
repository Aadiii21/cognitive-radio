// node docs/reports/build_reports.js   -> the three part reports and the master report (.docx) in docs/reports/
(async () => {
  await require("./part1")();
  await require("./part2")();
  await require("./part3")();
  await require("./master")();
})().catch((e) => { console.error(e); process.exit(1); });
