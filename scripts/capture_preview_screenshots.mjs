import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.PREVIEW_BASE_URL ?? "http://127.0.0.1:8000";
const artifactDir = process.env.PREVIEW_ARTIFACT_DIR ?? "e2e-artifacts";
const previewEmail = "preview@example.com";

async function fetchJson(url, init = {}) {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`Request failed for ${url}: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function capture(page, name, route, assertText) {
  const response = await page.goto(new URL(route, baseUrl).toString(), { waitUntil: "networkidle" });
  if (!response || !response.ok()) {
    throw new Error(`Navigation failed for ${route}`);
  }
  if (assertText) {
    const content = await page.content();
    if (!content.includes(assertText)) {
      throw new Error(`Expected to find \"${assertText}\" on ${route}`);
    }
  }
  await page.screenshot({ path: path.join(artifactDir, `${name}.png`), fullPage: true });
}

async function main() {
  await fs.mkdir(artifactDir, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });

  try {
    const auth = await fetchJson(new URL("/api/v1/auth/preview/login", baseUrl), {
      method: "POST",
    });

    await page.request.post(new URL("/api/v1/auth/preview/login", baseUrl).toString(), {
      data: { email: previewEmail },
    });

    const headers = { Authorization: `Bearer ${auth.access_token}` };
    const households = await fetchJson(new URL("/api/v1/households", baseUrl), { headers });
    const lists = await fetchJson(
      new URL(`/api/v1/households/${households[0].id}/lists`, baseUrl),
      { headers },
    );

    await capture(page, "preview", "/preview", "Preview Household");
    await capture(page, "login", "/login", "Login");
    await capture(page, "dashboard", "/", "Households and Lists");
    await capture(page, "list-detail", `/lists/${lists[0].id}`, "List");
  } finally {
    await browser.close();
  }

  const summary = [
    "## PR preview screenshots",
    "",
    "The seeded preview app passed the browser smoke flow and produced these screenshots:",
    "",
    "- `preview.png` — seeded preview data page",
    "- `login.png` — login route",
    "- `dashboard.png` — dashboard route",
    "- `list-detail.png` — seeded list detail route",
    "",
    "Download the **pr-preview-screenshots** artifact from this workflow run to inspect them.",
    "",
  ].join("\n");

  await fs.writeFile(path.join(artifactDir, "summary.md"), summary);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
