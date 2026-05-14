import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { chromium, devices } from "playwright";

const baseUrl = process.env.PREVIEW_BASE_URL ?? "http://127.0.0.1:8000";
const artifactDir = process.env.PREVIEW_ARTIFACT_DIR ?? "e2e-artifacts/ui-e2e";
const videoDir = path.join(artifactDir, "videos");
const seedPath = process.env.E2E_SEED_PATH ?? "app/fixtures/review_seed_e2e.json";
const deviceName = process.env.E2E_DEVICE ?? "desktop";
const knownDevices = new Map([["iphone", "iPhone 13"]]);
const staleBlueAccentTokens = [
  "20, 42, 87",
  "29, 184, 217",
  "79, 105, 129",
  "167, 203, 223",
  "223, 248, 253",
  "245, 251, 253",
];

function logStep(message) {
  console.log(`[ui-e2e] ${message}`);
}

async function resetDir(dir) {
  await fs.rm(dir, { recursive: true, force: true });
  await fs.mkdir(dir, { recursive: true });
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

function contextOptions() {
  const preset = knownDevices.get(deviceName);
  if (!preset) {
    return {
      viewport: { width: 1440, height: 1200 },
      recordVideo: {
        dir: videoDir,
        size: { width: 1440, height: 1200 },
      },
    };
  }

  const device = devices[preset];
  assert(device, `Unknown Playwright device preset ${preset}`);
  return {
    ...device,
    recordVideo: {
      dir: videoDir,
      size: device.viewport,
    },
  };
}

function toBase64(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  return normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
}

async function loadSeed() {
  const seed = JSON.parse(await fs.readFile(seedPath, "utf8"));
  assert(seed?.e2e, "Expected e2e metadata in seed fixture");
  assert(Array.isArray(seed?.users), "Expected users array in seed fixture");
  assert(Array.isArray(seed?.households), "Expected households array in seed fixture");
  return seed;
}

function fixtureUser(seed, email) {
  const user = seed.users.find((entry) => entry.email === email);
  assert(user, `Expected seeded user ${email}`);
  assert(user.passkey, `Expected seeded passkey for ${email}`);
  assert(user.passkey.private_key_pkcs8_b64, `Expected private key fixture for ${email}`);
  assert(user.passkey.user_handle_b64, `Expected user handle fixture for ${email}`);
  return user;
}

function fixtureAccount(seed, email) {
  const user = seed.users.find((entry) => entry.email === email);
  assert(user, `Expected seeded user ${email}`);
  return user;
}

function fixturePrimaryList(seed) {
  const household = seed.households.find((entry) => entry.name === seed.e2e.primary_household);
  assert(household, `Expected primary household ${seed.e2e.primary_household}`);
  const groceryList = household.lists.find((entry) => entry.name === seed.e2e.primary_list);
  assert(groceryList, `Expected primary list ${seed.e2e.primary_list}`);
  return groceryList;
}

async function apiJson(requestContext, url, options = {}) {
  const response = await requestContext.fetch(new URL(url, baseUrl).toString(), options);
  if (!response.ok()) {
    throw new Error(`Request failed for ${url}: ${response.status()} ${response.statusText()}`);
  }
  return response.json();
}

async function expectVisible(locator, message) {
  await locator.waitFor({ state: "visible" });
  assert(await locator.isVisible(), message);
}

async function expectHidden(locator, message) {
  await locator.waitFor({ state: "hidden" });
  assert(!(await locator.isVisible().catch(() => false)), message);
}

async function expectInViewport(locator, message) {
  await locator.waitFor({ state: "visible" });
  const isInViewport = await locator.evaluate(async (node) => {
    const isFullyVisible = () => {
      const rect = node.getBoundingClientRect();
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
      return (
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= viewportHeight &&
        rect.right <= viewportWidth
      );
    };
    if (isFullyVisible()) {
      return true;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 800));
    return isFullyVisible();
  });
  assert(isInViewport, message);
}

async function assertBrownWhiteAccentChrome(page) {
  logStep("Checking brown-white accent chrome");
  const matches = await page.evaluate((tokens) => {
    const staleMatches = [];
    for (const sheet of [...document.styleSheets]) {
      let rules = [];
      try {
        rules = [...sheet.cssRules];
      } catch {
        continue;
      }

      for (const rule of rules) {
        const cssText = rule.cssText || "";
        const token = tokens.find((entry) => cssText.includes(entry));
        if (token) {
          staleMatches.push(`stylesheet:${token}:${cssText.slice(0, 160)}`);
        }
      }
    }

    const selectors = [
      ".item-category-header",
      ".item-card",
      ".checked-items-load-more",
      ".item-suggestion",
      ".item-more-fields",
      ".floating-add-button",
      ".list-toast",
      ".category-radio-card",
    ];
    const properties = [
      "backgroundColor",
      "backgroundImage",
      "borderTopColor",
      "borderRightColor",
      "borderBottomColor",
      "borderLeftColor",
      "boxShadow",
    ];

    for (const selector of selectors) {
      for (const node of [...document.querySelectorAll(selector)]) {
        const styles = getComputedStyle(node);
        for (const property of properties) {
          const value = styles[property];
          const token = tokens.find((entry) => value.includes(entry));
          if (token) {
            staleMatches.push(`${selector}:${property}:${value}`);
          }
        }
      }
    }

    return staleMatches;
  }, staleBlueAccentTokens);

  assert.deepEqual(matches, [], "Expected list chrome to avoid stale blue accent colors");
}

async function assertHeaderActionsFitTranslatedLabels(page) {
  logStep("Checking mobile header action sizing with German labels");
  const originalViewport = page.viewportSize();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(() => {
    const settingsLink = document.querySelector('.app-header-actions .admin-link[href="/settings"]');
    const logoutButton = document.querySelector(".app-header-actions .logout-button");
    return Boolean(settingsLink && logoutButton);
  });

  const measurements = await page.evaluate(() => {
    const settingsLink = document.querySelector('.app-header-actions .admin-link[href="/settings"]');
    const logoutButton = document.querySelector(".app-header-actions .logout-button");
    if (!(settingsLink instanceof HTMLElement) || !(logoutButton instanceof HTMLElement)) {
      throw new Error("Expected settings and logout controls in the app header");
    }

    const controls = [
      [settingsLink, "Einstellungen"],
      [logoutButton, "Abmelden"],
    ];
    const originals = controls.map(([node]) => node.textContent);

    try {
      for (const [node, label] of controls) {
        node.textContent = label;
      }
      document.body.offsetWidth;
      return controls.map(([node]) => ({
        text: node.textContent?.trim() ?? "",
        clientWidth: node.clientWidth,
        scrollWidth: node.scrollWidth,
      }));
    } finally {
      controls.forEach(([node], index) => {
        node.textContent = originals[index];
      });
    }
  });

  if (originalViewport) {
    await page.setViewportSize(originalViewport);
  }

  for (const measurement of measurements) {
    assert(
      measurement.scrollWidth <= measurement.clientWidth,
      `${measurement.text} should fit in the mobile header button without clipping`,
    );
  }
}

async function assertLoginPageTabs(page) {
  const signInTab = page.getByRole("tab", { name: "Sign In" });
  const createAccountTab = page.getByRole("tab", { name: "Create Account" });
  await expectVisible(signInTab, "Expected the Sign In tab on the login page");
  await expectVisible(createAccountTab, "Expected the Create Account tab on the login page");
  await expectVisible(
    page.getByRole("heading", { name: "Sign In" }),
    "Expected the sign-in heading inside the active auth panel",
  );
  await expectVisible(
    page.getByRole("button", { name: "Sign in with passkey" }),
    "Expected the passkey sign-in button on the login page",
  );
}

async function screenshot(page, name) {
  await page.screenshot({ path: path.join(artifactDir, `${name}.png`), fullPage: true });
}

async function createVirtualAuthenticator(page) {
  const client = await page.context().newCDPSession(page);
  await client.send("WebAuthn.enable", { enableUI: false });
  const { authenticatorId } = await client.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      ctap2Version: "ctap2_1",
      transport: "usb",
      hasResidentKey: true,
      hasUserVerification: true,
      automaticPresenceSimulation: true,
      isUserVerified: true,
    },
  });
  await client.send("WebAuthn.setAutomaticPresenceSimulation", {
    authenticatorId,
    enabled: true,
  });
  await client.send("WebAuthn.setUserVerified", {
    authenticatorId,
    isUserVerified: true,
  });
  return { client, authenticatorId };
}

async function authenticatorCredentials(authenticator) {
  const { credentials } = await authenticator.client.send("WebAuthn.getCredentials", {
    authenticatorId: authenticator.authenticatorId,
  });
  return credentials;
}

async function removeCredential(authenticator, credentialId) {
  await authenticator.client.send("WebAuthn.removeCredential", {
    authenticatorId: authenticator.authenticatorId,
    credentialId,
  });
}

async function removeAuthenticator(authenticator) {
  await authenticator.client.send("WebAuthn.removeVirtualAuthenticator", {
    authenticatorId: authenticator.authenticatorId,
  });
}

async function installSeededPasskey(authenticator, user, rpId) {
  await authenticator.client.send("WebAuthn.addCredential", {
    authenticatorId: authenticator.authenticatorId,
    credential: {
      credentialId: toBase64(user.passkey.credential_id),
      isResidentCredential: true,
      rpId,
      privateKey: user.passkey.private_key_pkcs8_b64,
      userHandle: user.passkey.user_handle_b64,
      signCount: Number(user.passkey.sign_count ?? 0),
      userName: user.email,
      userDisplayName: user.display_name,
    },
  });
  const credentials = await authenticatorCredentials(authenticator);
  assert.equal(credentials.length, 1, `Expected seeded credential for ${user.email}`);
  return credentials[0];
}

async function passkeysFromSession(requestContext) {
  return apiJson(requestContext, "/api/v1/auth/passkeys");
}

async function openSettingsPage(page) {
  await page.getByRole("link", { name: "Settings" }).click();
  await page.waitForURL(/\/settings(\?|$)/);
}

async function runPasskeyManagementFlow(page, context, owner, rpId, authenticator) {
  logStep("Opening settings passkey management");
  await openSettingsPage(page);
  await expectVisible(
    page.getByRole("heading", { name: "Your passkeys" }),
    "Expected passkey management section",
  );

  const originalPasskeys = await passkeysFromSession(context.request);
  assert.equal(originalPasskeys.length, 1, "Expected one seeded passkey before adding another");
  await expectHidden(
    page.locator("[data-passkey-empty]"),
    "Expected passkey empty state to stay hidden when passkeys are rendered",
  );
  await expectVisible(
    page.locator(".passkey-row").first(),
    "Expected seeded passkey row in settings",
  );

  const seededCredential = (await authenticatorCredentials(authenticator))[0];
  assert(seededCredential, "Expected seeded credential in the virtual authenticator");
  await removeAuthenticator(authenticator);

  const secondAuthenticator = await createVirtualAuthenticator(page);

  logStep("Adding a second passkey through settings");
  const secondPasskeyName = "Laptop passkey";
  await page.getByRole("button", { name: "Add another passkey" }).click();
  await page.getByLabel("Name this passkey").fill(secondPasskeyName);
  await page.getByRole("button", { name: "Continue" }).click();
  await expectVisible(
    page.locator("[data-passkey-success]", { hasText: "Another passkey is ready to use." }),
    "Expected passkey add success message",
  );
  await expectVisible(
    page.locator(".passkey-row").nth(1),
    "Expected a second passkey row after enrollment",
  );

  const passkeysAfterAdd = await passkeysFromSession(context.request);
  assert.equal(passkeysAfterAdd.length, 2, "Expected backend to store the second passkey");
  assert.equal(passkeysAfterAdd[1].name, secondPasskeyName, "Expected backend to store the chosen passkey name");
  await expectVisible(
    page.locator(".passkey-row", { hasText: secondPasskeyName }),
    "Expected settings to show the chosen passkey name",
  );

  logStep("Renaming the new passkey after confirming it still works");
  const renamedPasskeyName = "Travel passkey";
  await page.locator(".passkey-row").nth(1).getByRole("button", { name: "Rename" }).click();
  await page.getByLabel("Rename this passkey").fill(renamedPasskeyName);
  await page.getByRole("button", { name: "Save and verify" }).click();
  await expectVisible(
    page.locator("[data-passkey-success]", {
      hasText: "Passkey renamed after confirming it still works.",
    }),
    "Expected passkey rename success message",
  );
  const passkeysAfterRename = await passkeysFromSession(context.request);
  assert.equal(passkeysAfterRename[1].name, renamedPasskeyName, "Expected backend to store the renamed passkey label");
  await expectVisible(
    page.locator(".passkey-row", { hasText: renamedPasskeyName }),
    "Expected settings to show the renamed passkey label",
  );

  const credentialsAfterAdd = await authenticatorCredentials(secondAuthenticator);
  assert.equal(
    credentialsAfterAdd.length,
    1,
    "Expected one credential on the second authenticator after enrollment",
  );
  const addedCredential = credentialsAfterAdd[0];
  assert(addedCredential, "Expected a newly enrolled passkey credential");

  const remainingAuthenticatorCredentials = await authenticatorCredentials(secondAuthenticator);
  assert.equal(
    remainingAuthenticatorCredentials.length,
    1,
    "Expected only the newly added passkey on the second authenticator",
  );
  assert.equal(
    remainingAuthenticatorCredentials[0].credentialId,
    addedCredential.credentialId,
    "Expected the second authenticator credential to be the newly added passkey",
  );

  logStep("Logging out and confirming the new passkey can log back in");
  await page.getByRole("button", { name: "Logout" }).click();
  await page.waitForURL(/\/login(\?|$)/);
  await loginFromLoginPage(page, new URL("/", baseUrl).toString());
  await expectVisible(
    page.getByRole("heading", { name: "Households and Lists" }),
    "Expected login with the second passkey to succeed",
  );

  await openSettingsPage(page);
  logStep("Deleting the original passkey using the second passkey as confirmation");
  await page.locator(".passkey-row").nth(0).getByRole("button", { name: "Delete" }).click();
  await expectVisible(
    page.locator("[data-passkey-delete-panel]", {
      hasText:
        "You must authenticate with another passkey to confirm you still have a working Passkey after deleting one.",
    }),
    "Expected passkey delete confirmation modal",
  );
  await page.getByRole("button", { name: "Continue to verification" }).click();
  await expectVisible(
    page.locator("[data-passkey-success]", {
      hasText: "Passkey deleted after confirming another one worked.",
    }),
    "Expected passkey delete success message",
  );

  const passkeysAfterDelete = await passkeysFromSession(context.request);
  assert.equal(passkeysAfterDelete.length, 1, "Expected one passkey to remain after deletion");
  await page.waitForFunction(() => {
    const rows = [...document.querySelectorAll(".passkey-row")];
    if (rows.length !== 1) {
      return false;
    }
    const deleteButton = rows[0].querySelector("[data-passkey-delete]");
    return Boolean(deleteButton?.disabled);
  });

  await screenshot(page, "passkey-management");
  logStep("Passkey management checks passed");
}

async function loginFromLoginPage(page, expectedUrlPattern) {
  await assertLoginPageTabs(page);
  const signInButton = page.getByRole("button", { name: "Sign in with passkey" });
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await signInButton.click();
    try {
      await page.waitForURL(expectedUrlPattern, {
        waitUntil: "commit",
        timeout: 10_000,
      });
      return;
    } catch (error) {
      if (attempt === 1 || !/\/login(\?|$)/.test(new URL(page.url()).pathname)) {
        throw error;
      }
    }
  }
}

async function loginFromRoot(page, user, expectedHeading) {
  await page.goto(new URL("/", baseUrl).toString(), { waitUntil: "networkidle" });
  await page.waitForURL(/\/login(\?|$)/);
  await screenshot(page, "redirect-login");
  await loginFromLoginPage(page, new URL("/", baseUrl).toString());
  await expectVisible(
    page.getByRole("heading", { name: expectedHeading }),
    `Expected heading ${expectedHeading}`,
  );
}

async function registerAccountFromLogin(page, { displayName, email }, expectedUrlPattern) {
  await page.goto(new URL("/", baseUrl).toString(), { waitUntil: "networkidle" });
  await page.waitForURL(/\/login(\?|$)/);
  await assertLoginPageTabs(page);
  await page.locator('[data-auth-tab-trigger="signup"]').click();
  await expectVisible(
    page.locator('[data-auth-tab-panel="signup"] h2'),
    "Expected the create account heading inside the active auth panel",
  );
  await page.locator('[data-passkey-register] input[name="display_name"]').fill(displayName);
  await page.locator('[data-passkey-register] input[name="email"]').fill(email);
  await page.locator("[data-passkey-register-button]").click();
  await page.waitForURL(expectedUrlPattern, { waitUntil: "commit", timeout: 10_000 });
}

async function loginAsAdmin(page, user) {
  await page.goto(new URL("/", baseUrl).toString(), { waitUntil: "networkidle" });
  await page.waitForURL(/\/login(\?|$)/);
  await loginFromLoginPage(page, /\/admin\/?$/);
  await expectVisible(page.getByText("Admin tools"), "Expected admin tools card after admin login");
}

async function runAdminTableControlsFlow(page) {
  logStep("Checking admin table sorting, page size persistence, and reset controls");
  await page.goto(new URL("/admin/user/list", baseUrl).toString(), { waitUntil: "networkidle" });
  await expectVisible(page.getByRole("link", { name: "50 / Page" }), "Expected 50 row default");

  await page.getByRole("link", { name: "50 / Page" }).click();
  await page.locator(".dropdown-menu .dropdown-item", { hasText: "100 / Page" }).click();
  await page.waitForURL(/\/admin\/user\/list\?pageSize=100/);

  await page.getByRole("link", { name: "Email" }).click();
  await page.waitForURL(/\/admin\/user\/list\?.*pageSize=100.*sortBy=email.*sort=asc/);

  await page.getByRole("link", { name: "Categories" }).click();
  await page.waitForURL(/\/admin\/category\/list\?pageSize=100/);
  await expectVisible(page.getByRole("link", { name: "100 / Page" }), "Expected page size to persist");

  await page.getByRole("link", { name: "Name" }).click();
  await page.waitForURL(/\/admin\/category\/list\?.*pageSize=100.*sortBy=name.*sort=asc/);

  await page.getByRole("link", { name: "Reset view" }).click();
  await page.waitForURL(new URL("/admin/category/list", baseUrl).toString());
  assert(!page.url().includes("?"), `Expected reset to clear admin table params, got ${page.url()}`);
}

async function runAdminPasskeyAddLinkFlow(page, seed, rpId) {
  const adminUser = fixtureUser(seed, "planini_admin@schaedler.rocks");
  const targetUser = fixtureAccount(seed, "review-neighbor@example.com");

  logStep("Checking that a normal user cannot access admin user management");
  await page.goto(new URL("/admin/user/list", baseUrl).toString(), { waitUntil: "networkidle" });
  await page.waitForURL(new URL("/", baseUrl).toString());
  await expectHidden(
    page.getByRole("link", { name: "Admin" }),
    "Expected no admin link for a normal signed-in user",
  );

  const adminContext = await page.context().browser().newContext({
    viewport: { width: 1440, height: 1200 },
  });
  const adminPage = await adminContext.newPage();
  const recipientContext = await page.context().browser().newContext({
    viewport: { width: 1440, height: 1200 },
  });
  const replayContext = await page.context().browser().newContext({
    viewport: { width: 1440, height: 1200 },
  });

  try {
    const adminAuthenticator = await createVirtualAuthenticator(adminPage);
    await installSeededPasskey(adminAuthenticator, adminUser, rpId);

    logStep("Signing in as admin and generating an add-passkey link from the user edit page");
    await loginAsAdmin(adminPage, adminUser);
    await runAdminTableControlsFlow(adminPage);
    await adminPage.goto(new URL("/admin/user/list", baseUrl).toString(), { waitUntil: "networkidle" });
    const targetUserRow = adminPage.locator("tr", { hasText: targetUser.email }).first();
    await expectVisible(
      targetUserRow,
      `Expected to find an admin user row for ${targetUser.email}`,
    );
    await targetUserRow.locator('a[href*="/admin/user/edit/"]').first().click();
    await adminPage.waitForURL(/\/admin\/user\/edit\/.+$/);
    await expectVisible(
      adminPage.getByRole("button", { name: "Generate add-passkey link" }),
      "Expected add-passkey link generator on the admin user edit page",
    );
    await adminPage.getByRole("button", { name: "Generate add-passkey link" }).click();
    await adminPage.waitForURL(/passkey_add_link=/);
    const generatedLink = await adminPage.locator("#passkey-add-link").inputValue();
    assert(
      generatedLink.includes("/passkey-add/"),
      `Expected generated admin link to use /passkey-add/, got ${generatedLink}`,
    );

    const recipientPage = await recipientContext.newPage();
    const recipientAuthenticator = await createVirtualAuthenticator(recipientPage);

    try {
      logStep("Following the generated add-passkey link and registering a passkey");
      await recipientPage.goto(generatedLink, { waitUntil: "networkidle" });
      await expectVisible(
        recipientPage.getByRole("heading", { name: "Add passkey" }),
        "Expected the add-passkey landing page from the generated admin link",
      );
      await recipientPage.getByRole("button", { name: "Create additional passkey" }).click();
      await recipientPage.waitForURL(new URL("/", baseUrl).toString(), { waitUntil: "commit" });
      await expectVisible(
        recipientPage.getByRole("heading", { name: "Households and Lists" }),
        "Expected the generated-link user to land in the normal app after enrollment",
      );
    } finally {
      await removeAuthenticator(recipientAuthenticator);
      await recipientPage.close();
    }

    logStep("Ensuring the generated add-passkey link is single-use");
    const replayPage = await replayContext.newPage();
    try {
      await replayPage.goto(generatedLink, { waitUntil: "networkidle" });
      await replayPage.waitForURL(/\/login(\?|$)/);
    } finally {
      await replayPage.close();
    }

    await screenshot(adminPage, "admin-user-passkey-link");
  } finally {
    await adminPage.close();
    await replayContext.close();
    await recipientContext.close();
    await adminContext.close();
  }
}

async function scenarioFromSeed(seed, requestContext) {
  const households = await apiJson(requestContext, "/api/v1/households");
  const household = households.find((entry) => entry.name === seed.e2e.primary_household);
  assert(household, `Expected household ${seed.e2e.primary_household} from seeded fixture`);
  const lists = await apiJson(requestContext, `/api/v1/households/${household.id}/lists`);
  const groceryList = lists.find((entry) => entry.name === seed.e2e.primary_list);
  assert(groceryList, `Expected seeded list ${seed.e2e.primary_list}`);
  const checkedStressList = lists.find((entry) => entry.name === seed.e2e.checked_stress_list);
  assert(checkedStressList, `Expected seeded list ${seed.e2e.checked_stress_list}`);
  return {
    checkedStressListId: checkedStressList.id,
    householdId: household.id,
    householdName: household.name,
    listId: groceryList.id,
    listName: groceryList.name,
  };
}

async function resetFixtureItems(requestContext, listId, expectedChecked) {
  const items = await apiJson(requestContext, `/api/v1/lists/${listId}/items`);
  for (const item of items) {
    if (item.name.startsWith("Fresh thing")) {
      await apiJson(requestContext, `/api/v1/items/${item.id}`, { method: "DELETE" });
      continue;
    }

    if (!expectedChecked.has(item.name)) {
      continue;
    }

    if (item.hidden_until) {
      await apiJson(requestContext, `/api/v1/items/${item.id}`, {
        method: "PATCH",
        data: { hidden_until: null },
      });
    }

    const shouldBeChecked = expectedChecked.get(item.name);
    if (Boolean(item.checked) === shouldBeChecked) {
      continue;
    }

    await apiJson(requestContext, `/api/v1/items/${item.id}/${shouldBeChecked ? "check" : "uncheck"}`, {
      method: "POST",
    });
  }
}

async function textList(locator) {
  return locator.evaluateAll((nodes) => nodes.map((node) => node.textContent?.trim() || ""));
}

function itemCard(page, text) {
  return page.locator(".item-card", { hasText: text }).first();
}

async function swipeItemRight(card) {
  await card.evaluate((node) => {
    const rect = node.getBoundingClientRect();
    const startX = rect.left + Math.min(24, rect.width * 0.18);
    const endX = Math.min(rect.right - 12, startX + 120);
    const y = rect.top + rect.height / 2;
    const base = {
      bubbles: true,
      cancelable: true,
      pointerId: 42,
      pointerType: "touch",
      isPrimary: true,
    };
    node.dispatchEvent(new PointerEvent("pointerdown", {
      ...base,
      buttons: 1,
      clientX: startX,
      clientY: y,
    }));
    node.dispatchEvent(new PointerEvent("pointermove", {
      ...base,
      buttons: 1,
      clientX: endX,
      clientY: y,
    }));
    node.dispatchEvent(new PointerEvent("pointerup", {
      ...base,
      buttons: 0,
      clientX: endX,
      clientY: y,
    }));
  });
}

async function revealCheckedItemCard(page, text) {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const card = itemCard(page, text);
    if (await card.isVisible()) {
      return card;
    }

    const loadMoreButton = page.locator(".checked-items-load-more button").first();
    if (!(await loadMoreButton.isVisible())) {
      break;
    }
    await loadMoreButton.click();
  }

  throw new Error(`Could not reveal checked item card for ${text}`);
}

async function expectCheckedCardCount(group, count) {
  await group.locator(".item-card").nth(count - 1).waitFor({ state: "visible" });
  assert.equal(await group.locator(".item-card").count(), count);
}

async function runCheckedStressListFlow(page, stressListUrl) {
  logStep("Checking large checked-off list pagination");
  await page.goto(stressListUrl, { waitUntil: "networkidle" });

  const checkedGroup = page
    .locator(".item-category-group")
    .filter({ has: page.locator(".item-category-header h3", { hasText: "Checked off" }) })
    .first();
  const headingMeta = checkedGroup.locator(".item-category-header .item-category-meta");
  const loadMoreButton = checkedGroup.locator(".checked-items-load-more button");
  const loadMoreMeta = checkedGroup.locator(".checked-items-load-more .item-category-meta");

  await expectVisible(checkedGroup, "Expected checked-off group on large checked list");
  await expectCheckedCardCount(checkedGroup, 10);
  assert.equal(await headingMeta.textContent(), "258 items");
  assert.equal(await loadMoreButton.textContent(), "Load 100 more");
  assert.equal(await loadMoreMeta.textContent(), "248 older items not loaded");
  await assertBrownWhiteAccentChrome(page);

  await loadMoreButton.click();
  await expectCheckedCardCount(checkedGroup, 110);
  assert.equal(await headingMeta.textContent(), "258 items");
  assert.equal(await loadMoreButton.textContent(), "Load 100 more");
  assert.equal(await loadMoreMeta.textContent(), "148 older items not loaded");

  await loadMoreButton.click();
  await expectCheckedCardCount(checkedGroup, 210);
  assert.equal(await headingMeta.textContent(), "258 items");
  assert.equal(await loadMoreButton.textContent(), "Load 48 more");
  assert.equal(await loadMoreMeta.textContent(), "48 older items not loaded");

  await loadMoreButton.click();
  await expectCheckedCardCount(checkedGroup, 258);
  assert.equal(await headingMeta.textContent(), "258 items");
  assert.equal(await checkedGroup.locator(".checked-items-load-more").count(), 0);
}

async function runOfflineSyncFlow(page, requestContext, listId) {
  logStep("Checking offline list item save and resync");
  const offlineName = `Fresh thing offline ${Date.now()}`;
  const addForm = page.locator("[data-item-form]");

  await page.context().setOffline(true);
  try {
    await page.getByRole("button", { name: "Add item" }).click();
    await addForm.getByLabel("Item name").fill(offlineName);
    await page.locator(".add-item-save-button").click();
    await expectVisible(
      page.locator("[data-list-error]", { hasText: "Offline. Changes saved locally" }),
      "Offline add should show local-only error",
    );
    const offlineCard = itemCard(page, offlineName);
    await expectVisible(offlineCard, "Offline-created item should render immediately");
    await offlineCard.getByRole("button").first().click();
    await expectVisible(
      page.locator("[data-list-error]", { hasText: "Offline. Changes saved locally" }),
      "Offline check should keep local-only error",
    );
  } finally {
    await page.context().setOffline(false);
  }

  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expectVisible(
    page.locator("[data-list-success]", { hasText: "Saved offline changes synced." }),
    "Offline changes should sync after reconnect",
  );
  const items = await apiJson(requestContext, `/api/v1/lists/${listId}/items`);
  const syncedItem = items.find((item) => item.name === offlineName);
  assert(syncedItem, "Expected offline-created item to exist after sync");
  assert.equal(syncedItem.checked, true, "Expected offline checked state to sync");
}

function extractInviteToken(inviteUrl) {
  const invitePath = new URL(inviteUrl).pathname;
  return invitePath.split("/").filter(Boolean).at(-1);
}

async function runInviteFlow(ownerPage, browser, scenario, seed, rpId) {
  logStep("Creating and accepting a household invite");
  await ownerPage.goto(new URL("/?dashboard=1", baseUrl).toString(), { waitUntil: "networkidle" });
  await expectVisible(
    ownerPage.getByRole("heading", { name: "Households and Lists" }),
    "Expected dashboard heading",
  );

  const ownerHouseholdCard = ownerPage
    .locator(".household-card", { hasText: scenario.householdName })
    .first();
  await expectVisible(ownerHouseholdCard, "Expected seeded household card on dashboard");

  await ownerHouseholdCard.getByRole("button", { name: "Create invite link" }).click();
  const inviteInput = ownerHouseholdCard.locator(
    `[data-invite-link-input="${scenario.householdId}"]`,
  );
  await expectVisible(inviteInput, "Expected invite link field after creating invite");
  const inviteUrl = await inviteInput.inputValue();
  assert(inviteUrl.includes("/invite/"), "Expected invite URL");
  const inviteToken = extractInviteToken(inviteUrl);
  assert(inviteToken, "Expected invite token");

  const inviteeContext = await browser.newContext(contextOptions());
  const inviteePage = await inviteeContext.newPage();
  const invitee = fixtureUser(seed, seed.e2e.invitee_email);

  try {
    const inviteeAuthenticator = await createVirtualAuthenticator(inviteePage);
    await installSeededPasskey(inviteeAuthenticator, invitee, rpId);
    await inviteePage.goto(new URL("/", baseUrl).toString(), { waitUntil: "networkidle" });
    await inviteePage.waitForURL(/\/login(\?|$)/);
    await loginFromLoginPage(inviteePage, new URL("/", baseUrl).toString());
    await expectVisible(
      inviteePage.getByRole("heading", { name: "Households and Lists" }),
      "Invitee should reach the dashboard before accepting an invite",
    );
    assert.equal(
      await inviteePage.locator(".household-card", { hasText: scenario.householdName }).count(),
      0,
      "Invitee should not see the owner's household before accepting an invite",
    );

    await inviteeContext.request.post(new URL("/api/v1/auth/logout", baseUrl).toString());
    await inviteePage.goto(inviteUrl, { waitUntil: "networkidle" });
    await inviteePage.waitForURL(/\/login\?next=%2Finvite%2F|\/login\?next=\/invite\//);
    await screenshot(inviteePage, "invite-redirect-login");

    await loginFromLoginPage(inviteePage, /\/invite\//);
    await expectVisible(
      inviteePage.getByRole("heading", { name: "Join a shared grocery space" }),
      "Expected invite details page after passkey login",
    );
    await expectVisible(
      inviteePage.getByRole("heading", { name: scenario.householdName }),
      "Expected invite page household name",
    );
    await inviteePage.getByRole("button", { name: "Accept invite" }).click();
    await inviteePage.waitForURL(new URL("/", baseUrl).toString());
    const acceptedHouseholdCard = inviteePage
      .locator(".household-card", { hasText: scenario.householdName })
      .filter({ hasText: scenario.listName })
      .first();
    await expectVisible(
      acceptedHouseholdCard,
      "Invitee should see the seeded list after accepting the invite",
    );
    await expectVisible(
      acceptedHouseholdCard.getByRole("link", { name: "Open list" }).first(),
      "Invitee should be able to reach the seeded list after accepting the invite",
    );
    await screenshot(inviteePage, "invite-accepted");
  } finally {
    await inviteeContext.close();
  }
}

async function runDashboardEmptyStateFlow(browser) {
  logStep("Checking dashboard empty-state add cards");
  const context = await browser.newContext(contextOptions());
  const page = await context.newPage();
  const authenticator = await createVirtualAuthenticator(page);
  const timestamp = Date.now();
  const emptyStateAccount = {
    displayName: `Dashboard Empty ${timestamp}`,
    email: `dashboard-empty-${timestamp}@example.com`,
  };

  try {
    await registerAccountFromLogin(page, emptyStateAccount, new URL("/", baseUrl).toString());
    await expectVisible(
      page.getByRole("heading", { name: "Households and Lists" }),
      "Expected a brand-new account to land on the dashboard",
    );

    const ordering = await page.evaluate(() => {
      const lists = document.querySelector(".dashboard-lists");
      const organized = document.querySelector("[data-dashboard-organized]");
      if (!(lists instanceof HTMLElement) || !(organized instanceof HTMLElement)) {
        return null;
      }
      return lists.compareDocumentPosition(organized);
    });
    assert(ordering !== null, "Expected dashboard lists section and organized section");
    assert(
      Boolean(ordering & 4),
      "Expected the organized section to appear after the lists section",
    );

    const emptyHouseholdButton = page.locator(
      '[data-dashboard-empty] [data-dashboard-add-option="household"]',
    );
    await expectVisible(emptyHouseholdButton, "Expected add-household action card when no households exist");
    await emptyHouseholdButton.click();
    await expectVisible(
      page.getByRole("heading", { name: "Add household" }),
      "Expected add-household panel from the empty-state card",
    );

    const householdName = "Fresh household";
    await page.getByLabel("Household name").fill(householdName);
    await page.getByRole("button", { name: "Create household" }).click();
    const newHouseholdCard = page.locator(".household-card", { hasText: householdName }).first();
    await expectVisible(newHouseholdCard, "Expected the new household to appear on the dashboard");

    const emptyListButton = newHouseholdCard.locator('[data-dashboard-add-option="list"]');
    await expectVisible(emptyListButton, "Expected add-list action card for a household without lists");
    await emptyListButton.click();
    await expectVisible(
      page.getByRole("heading", { name: "Add list to household" }),
      "Expected add-list panel from the empty-state card",
    );

    const listName = "Fresh list";
    await page.getByLabel("List name").fill(listName);
    await page.getByRole("button", { name: "Create list" }).click();
    await page.waitForURL(/\/lists\/.+$/);
    await expectVisible(
      page.getByRole("heading", { name: listName }),
      "Expected the new list detail page after creating a list from the empty-state card",
    );
    await screenshot(page, "dashboard-empty-state-actions");
  } finally {
    await removeAuthenticator(authenticator);
    await context.close();
  }
}

async function main() {
  logStep(`Preparing artifacts in ${artifactDir}`);
  await resetDir(artifactDir);
  await ensureDir(videoDir);

  logStep(`Loading seed fixture from ${seedPath}`);
  const seed = await loadSeed();
  const rpId = process.env.WEBAUTHN_RP_ID ?? seed.e2e.rp_id ?? new URL(baseUrl).hostname;
  const owner = fixtureUser(seed, seed.e2e.owner_email);
  const seededPrimaryList = fixturePrimaryList(seed);
  const expectedChecked = new Map(
    seededPrimaryList.items.map((item) => [item.name, Boolean(item.checked)]),
  );

  const browser = await chromium.launch();
  const context = await browser.newContext(contextOptions());
  const page = await context.newPage();

  try {
    logStep(`Launching browser flow against ${baseUrl}`);
    const authenticator = await createVirtualAuthenticator(page);
    await installSeededPasskey(authenticator, owner, rpId);
    logStep("Signing in with the seeded owner passkey");
    await loginFromRoot(page, owner, "Households and Lists");
    await assertHeaderActionsFitTranslatedLabels(page);
    await runAdminPasskeyAddLinkFlow(page, seed, rpId);
    await runPasskeyManagementFlow(page, context, owner, rpId, authenticator);
    await runDashboardEmptyStateFlow(browser);

    const scenario = await scenarioFromSeed(seed, context.request);
    logStep(`Resetting seeded list state for ${scenario.listName}`);
    await resetFixtureItems(context.request, scenario.listId, expectedChecked);
    const listUrl = new URL(`/lists/${scenario.listId}`, baseUrl).toString();
    const checkedStressListUrl = new URL(`/lists/${scenario.checkedStressListId}`, baseUrl).toString();

    if (owner.is_admin) {
      await expectVisible(page.getByRole("link", { name: "Admin" }), "Expected admin link");

      const adminPage = await context.newPage();
      await adminPage.goto(new URL("/admin", baseUrl).toString(), { waitUntil: "networkidle" });
      await expectVisible(
        adminPage.getByRole("link", { name: "Go to application" }),
        "Expected Go to application link in admin",
      );
      await screenshot(adminPage, "admin-home");
      await adminPage.close();
    }

    const pageTwo = await context.newPage();
    await Promise.all([
      page.goto(listUrl, { waitUntil: "networkidle" }),
      pageTwo.goto(listUrl, { waitUntil: "networkidle" }),
    ]);

    const addForm = page.locator("[data-item-form]");
    const editForm = page.locator("[data-item-edit-form]");

    logStep("Running main list interaction flow");
    await expectVisible(page.getByRole("button", { name: "Add item" }), "Expected floating add button");
    await expectVisible(page.locator(".item-card", { hasText: "Spaghetti" }), "Expected seeded items to load");
    await assertBrownWhiteAccentChrome(page);

    if (deviceName === "desktop") {
      await page.keyboard.press("Enter");
      await expectVisible(page.locator("[data-item-panel]"), "Enter should open add modal");
    } else {
      await page.getByRole("button", { name: "Add item" }).click();
      await expectVisible(page.locator("[data-item-panel]"), "Add button should open add modal");
    }
    await addForm.getByLabel("Item name").fill("Spag");
    const activeSuggestion = addForm.locator(".item-suggestion", { hasText: "Spaghetti" });
    await expectVisible(activeSuggestion, "Expected duplicate suggestion for active item");
    await activeSuggestion.locator("button").click();
    await expectHidden(page.locator("[data-item-panel]"), "Suggestion reuse should close add modal");
    await page.waitForSelector('[data-item-card].is-highlighted', { timeout: 3000 });

    const spaghettiCard = itemCard(page, "Spaghetti");
    if (deviceName === "desktop") {
      await spaghettiCard.getByRole("button", { name: "More actions for Spaghetti" }).click();
      await spaghettiCard.getByRole("button", { name: "Hide item for 4h" }).click();
    } else {
      await swipeItemRight(spaghettiCard);
    }
    await expectVisible(
      page.locator("[data-list-toast]", { hasText: "Spaghetti hidden for 4 hours." }),
      "Expected hide-for-later toast",
    );
    const hiddenGroup = page.locator(".item-hidden-group");
    const hiddenSpaghetti = hiddenGroup.locator(".item-card", { hasText: "Spaghetti" });
    await expectVisible(hiddenSpaghetti, "Hidden item should move into the hidden section");
    await expectVisible(
      hiddenSpaghetti.getByRole("button", { name: "Show Spaghetti now" }),
      "Hidden item should expose a time button for unhiding",
    );
    await pageTwo.waitForFunction(
      () => {
        const hiddenGroup = document.querySelector(".item-hidden-group");
        return Boolean(hiddenGroup?.textContent?.includes("Spaghetti"));
      },
      { timeout: 5000 },
    );
    await hiddenSpaghetti.getByRole("button", { name: "Show Spaghetti now" }).click();
    await expectHidden(hiddenGroup.locator(".item-card", { hasText: "Spaghetti" }), "Time button should unhide item");
    await expectVisible(itemCard(page, "Spaghetti"), "Unhidden item should return to normal categories");
    await pageTwo.waitForFunction(
      () => {
        const hiddenGroup = document.querySelector(".item-hidden-group");
        if (hiddenGroup?.textContent?.includes("Spaghetti")) {
          return false;
        }
        return [...document.querySelectorAll(".item-card")].some((node) =>
          node.textContent?.includes("Spaghetti"),
        );
      },
      { timeout: 5000 },
    );

    await page.getByRole("button", { name: "Add item" }).click();
    await addForm.getByLabel("Item name").fill("Brot");
    const checkedSuggestion = addForm.locator(".item-suggestion", { hasText: "Brot" });
    await expectVisible(checkedSuggestion, "Expected suggestion for checked duplicate item");
    await checkedSuggestion.locator("button").click();
    await expectVisible(
      page.locator("[data-list-toast]", { hasText: "Brot added back to the list." }),
      "Expected re-add toast",
    );
    await page.locator(".item-category-header h3", { hasText: "Checked off" }).waitFor({ state: "hidden" });
    await expectVisible(page.locator(".item-card", { hasText: "Brot" }), "Brot should be active again");

    const backwarenHeader = page.locator(".item-category-header h3", { hasText: "Backwaren" }).first();
    await expectVisible(backwarenHeader, "Expected Backwaren section");

    const looseItemCard = page.locator(".item-card", { hasText: "Loose item" });
    await looseItemCard.getByRole("button").first().click();
    await expectVisible(
      page.locator("[data-list-toast]", { hasText: "Loose item checked." }),
      "Expected check toast",
    );
    await page.locator("[data-list-toast-undo]").click();
    await expectVisible(
      page.locator(".item-card", { hasText: "Loose item" }),
      "Undo should restore unchecked item",
    );

    const tofuCard = itemCard(page, "Tofu");
    await tofuCard.getByRole("button").first().click();
    await expectVisible(
      page.locator("[data-list-toast]", { hasText: "Tofu checked." }),
      "Expected tofu check toast",
    );
    await page.waitForFunction(
      () => [...document.querySelectorAll(".item-category-header h3")].some((node) => node.textContent?.includes("Checked off")),
    );
    await pageTwo.waitForFunction(
      () => {
        const card = [...document.querySelectorAll(".item-card")].find((node) =>
          node.textContent?.includes("Tofu"),
        );
        return Boolean(card && card.classList.contains("is-checked"));
      },
      { timeout: 5000 },
    );

    const eierCard = itemCard(page, "Eier");
    await eierCard.getByRole("button").first().click();
    await expectVisible(
      page.locator("[data-list-toast]", { hasText: "Eier checked." }),
      "Expected Eier check toast",
    );
    await page.waitForFunction(
      () => {
        const groups = [...document.querySelectorAll(".item-category-group")];
        const checkedGroup = groups.find((group) =>
          group.querySelector(".item-category-header h3")?.textContent?.includes("Checked off"),
        );
        if (!checkedGroup) {
          return false;
        }
        const checkedNames = [...checkedGroup.querySelectorAll(".item-card .item-name")].map(
          (node) => node.textContent?.trim(),
        );
        return checkedNames[0] === "Eier" && checkedNames.includes("Tofu");
      },
      { timeout: 5000 },
    );
    const checkedNames = await textList(
      page.locator(".item-category-group:last-child .item-card .item-name"),
    );
    assert.equal(checkedNames[0], "Eier", "Most recently checked item should be first in checked section");
    assert(checkedNames.includes("Tofu"), "Expected previously checked item in checked section");

    const hackfleischCard = await revealCheckedItemCard(page, "Hackfleisch");
    await hackfleischCard.click();
    const hackfleischEditPanel = page.locator("[data-item-edit-panel]", { hasText: "Hackfleisch" });
    await expectVisible(hackfleischEditPanel, "Expected Hackfleisch edit modal before deleting");
    await hackfleischEditPanel.locator("[data-item-edit-delete]").click();
    await expectVisible(
      page.locator("[data-list-toast]", { hasText: /Hackfleisch (deleted|wurde gelöscht)\./ }),
      "Expected delete toast",
    );
    await page.locator("[data-list-toast-undo]").click();
    await expectVisible(
      page.locator(".item-card", { hasText: "Hackfleisch" }),
      "Undo should restore deleted item",
    );

    await itemCard(page, "Tomaten").click();
    await expectVisible(
      page.locator("[data-item-edit-panel]").getByRole("heading", { name: "Tomaten" }),
      "Clicking item should open edit modal",
    );
    const editSearch = editForm.locator("[data-item-edit-category-search]");
    await editSearch.fill("brot");
    await expectVisible(
      editForm.locator(".category-radio-option", { hasText: "Backwaren" }),
      "Alias search should find Backwaren",
    );
    const aliasTexts = await textList(
      editForm.locator(".category-radio-option .category-radio-copy span"),
    );
    assert(!aliasTexts.some((text) => text.includes("Also found as")), "Alias helper text should stay hidden");
    await editForm.locator(".category-radio-option", { hasText: "Backwaren" }).click();
    await editForm.locator('input[name="quantity_text"]').fill("4 loaves");
    await editForm.locator('input[name="note"]').fill("for the weekend");
    await editForm.getByRole("button", { name: "Save changes" }).click();
    await expectVisible(
      page.locator("[data-list-success]", { hasText: "Item updated." }),
      "Expected item update success before closing the edit modal",
    );
    await page.locator("[data-item-edit-panel] .add-item-close[data-item-edit-close]").click();
    await expectHidden(page.locator("[data-item-edit-overlay]"), "Edit modal should close before opening settings");
    await expectVisible(itemCard(page, "Tomaten"), "Updated item should remain visible");
    await expectVisible(
      itemCard(page, "Tomaten").locator(".item-meta", { hasText: "4 loaves" }),
      "Updated quantity should render",
    );

    await page.getByRole("button", { name: "Open list settings" }).click();
    await expectVisible(page.getByRole("heading", { name: "Category order" }), "Expected settings modal");
    const topCategoryBefore = (
      await textList(page.locator(".item-category-group > .item-category-header h3"))
    ).slice(0, 3);
    assert.equal(topCategoryBefore[0], "Uncategorized", "Uncategorized should stay on top");

    const backwarenSettingsRow = page.locator(".settings-category-row", { hasText: "Backwaren" });
    for (let i = 0; i < 4; i += 1) {
      await backwarenSettingsRow.getByRole("button", { name: /Move Backwaren up/i }).click();
      await page.waitForTimeout(150);
    }
    await page.locator("[data-list-settings-panel] .add-item-close").click();

    await page.waitForFunction(
      () => {
        const headers = [...document.querySelectorAll(".item-category-group > .item-category-header h3")].map(
          (node) => node.textContent?.trim(),
        );
        return headers.indexOf("Backwaren") > -1 && headers.indexOf("Backwaren") < headers.indexOf("Nudeln");
      },
      { timeout: 5000 },
    );
    await pageTwo.waitForFunction(
      () => {
        const headers = [...document.querySelectorAll(".item-category-group > .item-category-header h3")].map(
          (node) => node.textContent?.trim(),
        );
        return headers.indexOf("Backwaren") > -1 && headers.indexOf("Backwaren") < headers.indexOf("Nudeln");
      },
      { timeout: 5000 },
    );

    await page.getByRole("button", { name: "Add item" }).click();
    const freshThingName = `Fresh thing ${Date.now()}`;
    await addForm.getByLabel("Item name").fill(freshThingName);
    await addForm.locator(".item-more-fields summary").click();
    await addForm.locator("[data-item-category-search]").fill("brot");
    await addForm.locator(".category-radio-option", { hasText: "Backwaren" }).click();
    await addForm.locator('input[name="quantity_text"]').fill("1");
    await page.locator(".add-item-save-button").click();
    const freshThingCard = itemCard(page, freshThingName);
    await expectVisible(freshThingCard, "Expected newly added item");
    await expectVisible(
      page.locator(".item-card.is-highlighted", { hasText: freshThingName }),
      "New item should be highlighted after saving",
    );
    await expectInViewport(freshThingCard, "New item should be scrolled into view after saving");
    await expectVisible(
      page
        .locator(".item-category-group", { hasText: "Backwaren" })
        .locator(".item-card", { hasText: freshThingName }),
      "New item should land in the Backwaren section",
    );

    const toast = page.locator("[data-list-toast]");
    await freshThingCard.getByRole("button").first().click();
    await expectVisible(toast, "Expected temporary undo toast");
    await page.waitForTimeout(10500);
    await expectHidden(toast, "Undo toast should disappear after timeout");

    await runOfflineSyncFlow(page, context.request, scenario.listId);

    await runCheckedStressListFlow(page, checkedStressListUrl);

    await runInviteFlow(page, browser, scenario, seed, rpId);

    await screenshot(page, "ui-e2e-final");
    await screenshot(pageTwo, "ui-e2e-second-client");
    logStep("Browser UI e2e completed successfully");
  } catch (error) {
    logStep(`Browser UI e2e failed: ${error instanceof Error ? error.message : String(error)}`);
    await screenshot(page, "ui-e2e-failure-main").catch(() => {});
    throw error;
  } finally {
    await browser.close();
  }

  const summary = [
    "## UI E2E",
    "",
    `Browser UI flow passed for ${deviceName} using seeded real database data and passkey auth for route rendering, login gating, multi-passkey enrollment and deletion, add/edit flows, duplicate suggestions, undo toasts, category alias search, admin navigation, websocket updates, and household invite acceptance.`,
    "",
  ].join("\n");
  await fs.writeFile(path.join(artifactDir, "summary.md"), summary);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
