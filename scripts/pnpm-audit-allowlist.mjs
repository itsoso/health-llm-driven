import { stdin, stdout, stderr } from "node:process";

const allowedIds = new Set(["1088948", "1093404", "1105440"]);

let input = "";
stdin.setEncoding("utf8");
stdin.on("data", (chunk) => {
  input += chunk;
});

stdin.on("end", () => {
  if (!input.trim()) {
    stderr.write("pnpm audit output is empty\n");
    process.exit(2);
  }

  let report;
  try {
    report = JSON.parse(input);
  } catch (error) {
    stderr.write(`Failed to parse pnpm audit JSON: ${error}\n`);
    process.exit(2);
  }

  const advisories = report.advisories ?? {};
  const advisoryIds = Object.keys(advisories);
  const blocked = advisoryIds.filter((id) => !allowedIds.has(id));

  if (blocked.length > 0) {
    stderr.write(
      `Unexpected advisories: ${blocked.join(", ")}\n`
    );
    process.exit(1);
  }

  stdout.write("pnpm audit passed with allowlisted advisories only\n");
  process.exit(0);
});
