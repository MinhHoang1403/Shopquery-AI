import { expect, test } from "@playwright/test";

const env = (globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
}).process?.env ?? {};

test.use({ storageState: { cookies: [], origins: [] }, trace: "off", screenshot: "off", video: "off" });

test("two approved synthetic SQL JOIN questions, one per live provider", async ({ page, request }, info) => {
  test.skip(env.SHOPQUERY_JOIN_TWO_PROBES !== "approved", "Requires a new explicit two-probe budget");
  test.setTimeout(330_000);
  expect(info.project.name).toBe("desktop-1440");
  expect(info.retry).toBe(0);
  expect(new URL(info.project.use.baseURL as string).origin).toBe("http://127.0.0.1:8080");
  expect(info.outputDir.replaceAll("\\", "/").toLowerCase())
    .toContain("c:/work/shopquery-backups/live-join-providers-");
  expect((env.PLAYWRIGHT_JSON_OUTPUT_FILE ?? "").replaceAll("\\", "/").toLowerCase())
    .toContain("c:/work/shopquery-backups/live-join-providers-");
  const threeTables = env.SHOPQUERY_JOIN_THREE_TABLES === "1";
  const question = threeTables
    ? "Cho biết tên khóa học, tổng tiền đã thanh toán và số lần thanh toán của từng khóa học, kết hợp payments, students và courses."
    : "Cho biết tên sinh viên, tổng tiền đã thanh toán và số lần thanh toán của từng sinh viên.";
  const files = threeTables ? [
    ["courses.csv", "Course id,Course title\nC1,SQL\nC2,RAG\nC3,Math\n"],
    ["students.csv", "Student id,Student name,Course id\nS1,An,C1\nS2,Binh,C1\nS3,Chi,C2\nS4,Dung,C2\nS5,Em,C3\n"],
    ["payments.csv", "Payment id,Student id,Amount paid\nP1,S1,20.00\nP2,S1,0.00\nP3,S2,0.00\nP4,S3,\nP5,S4,\nP6,S5,12.50\nP7,S5,0.00\n"],
  ] : [
    ["students.csv", "Student id,Student name\nS1,An\nS2,Binh\nS3,Chi\n"],
    ["payments.csv", "Payment id,Student id,Amount paid\nP1,S1,20.00\nP2,S1,0.00\nP3,S2,0.00\nP4,S3,\nP5,S3,\n"],
  ];
  const attempted: string[] = [];
  const ledger = () => JSON.stringify({ question, tableCount: files.length, attempted, logicalGenerationUpperBound: attempted.length * 3,
    embeddingCalls: 0, automaticChatRetries: 0, transportRequestCount: "not instrumented" }, null, 2);
  await info.attach("budget-initial", { body: ledger(), contentType: "application/json" });
  await page.route("**/api/guest/chat", async (route) => {
    const body = route.request().postDataJSON();
    if (!(["inetcloud-knowledge", "gemini"].includes(body.model_id)) || attempted.includes(body.model_id)
        || attempted.length >= 2 || body.message !== question) {
      await route.abort();
      throw new Error("Refused an unapproved or duplicate provider probe");
    }
    attempted.push(body.model_id);
    await info.attach(`attempt-${body.model_id}`, { body: ledger(), contentType: "application/json" });
    await route.continue();
  });
  const sessionResponse = page.waitForResponse((r) => r.url().endsWith("/api/guest/session") && r.request().method() === "POST");
  await page.goto("/");
  const session = await (await sessionResponse).json();
  expect(session.ai_enabled).toBe(true);
  expect(session.sql_join_v1_enabled).toBe(true);
  expect(session.gemini_fallback_enabled).toBe(false);
  const headers = { Origin: "http://127.0.0.1:8080", "X-Guest-Token": session.token, "X-Guest-CSRF": session.csrf_token };
  try {
    const menu = page.getByRole("button", { name: "Mở thanh điều hướng", exact: true });
    if (await menu.isVisible()) await menu.click();
    await page.getByRole("button", { name: "Tệp tạm thời", exact: true }).click();
    for (const [name, content] of files) {
      await page.locator("#guest-file").evaluate((node, file) => {
        const transfer = new DataTransfer();
        transfer.items.add(new File([file.content], file.name, { type: "text/csv" }));
        (node as HTMLInputElement).files = transfer.files;
        node.dispatchEvent(new Event("change", { bubbles: true }));
      }, { name, content });
      await expect(page.locator(".preview-panel")).toContainText(name);
      const imported = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/guest/files" && r.request().method() === "POST");
      await page.getByRole("button", { name: "Dùng tệp trong phiên này", exact: true }).click();
      expect((await imported).status()).toBe(200);
      await expect(page.locator(".guest-file-list")).toContainText(name);
    }
    await expect(page.getByText("N:1 · Đã kiểm chứng · Tự động", { exact: true })).toHaveCount(threeTables ? 2 : 1);
    const relations = await (await request.get("/api/guest/relationships", { headers })).json();
    expect(relations.relationships).toHaveLength(threeTables ? 2 : 1);
    for (const relation of relations.relationships) {
      expect(relation).toMatchObject({ valid: true, origin: "automatic", confirmed: false,
        cardinality: "many-to-one", orphan_rows: 0 });
    }
    expect(relations.relationships.map((r: { source_rows: number; target_rows: number }) => [r.source_rows, r.target_rows]))
      .toEqual(threeTables ? [[5, 3], [7, 5]] : [[5, 3]]);
    await info.attach("relationship", { body: JSON.stringify(relations, null, 2), contentType: "application/json" });
    await page.getByRole("button", { name: "Đóng", exact: true }).last().click();
    for (const model of ["inetcloud-knowledge", "gemini"]) {
      await page.getByLabel("Chọn mô hình AI").selectOption(model);
      await page.getByLabel("Nhập câu hỏi cho ShopQuery AI").fill(question);
      const completed = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/guest/chat" && r.request().method() === "POST", { timeout: 145_000 });
      await page.getByLabel("Nhập câu hỏi cho ShopQuery AI").press("Enter");
      const response = await completed;
      const body = await response.json();
      await info.attach(model, { body: JSON.stringify({ status: response.status(), response: body.response ?? body }, null, 2), contentType: "application/json" });
      expect.soft(response.status()).toBe(200);
      if (response.ok() && body.response) {
        expect.soft(body.response.requested_model).toBe(model);
        expect.soft(body.response.used_model).toBe(model);
        expect.soft(body.response.fallback_used).toBe(false);
        expect.soft(body.response.error).toBeNull();
        expect.soft(body.response.route).toBe("SQL");
        if (body.response.route === "SQL") {
          expect.soft(body.response.sql).toContain("INNER JOIN");
          expect.soft((body.response.sql.match(/INNER JOIN/g) ?? []).length).toBe(threeTables ? 2 : 1);
          expect.soft(body.response.rows).toHaveLength(3);
          expect.soft(body.response.sources).toEqual([]);
          const sql = body.response.sql as string;
          const totalKey = sql.match(/SUM\([^)]*\)\s+AS\s+"?([a-z_]\w*)/i)?.[1] ?? "sum";
          const attribute = threeTables ? "course_title" : "student_name";
          const nameKey = sql.match(new RegExp(`\\b${attribute}"?\\s+AS\\s+"?([a-z_]\\w*)`, "i"))?.[1] ?? attribute;
          const actual = body.response.rows.map((row: Record<string, unknown>) => [
            row[nameKey], row[totalKey], row.fact_row_count ?? row.matched_row_count,
          ]).sort((a: unknown[], b: unknown[]) => String(a[0]).localeCompare(String(b[0])));
          expect.soft(actual).toEqual(threeTables
            ? [["Math", "12.50", 2], ["RAG", null, 2], ["SQL", "20.00", 3]]
            : [["An", "20.00", 2], ["Binh", "0.00", 1], ["Chi", null, 2]]);
        }
      }
      await expect(page.getByLabel("Chọn mô hình AI")).toBeEnabled();
      const answer = page.locator(".message--assistant").last();
      await answer.scrollIntoViewIfNeeded();
      await info.attach(`${model}-visible-answer`, { body: await answer.innerText(), contentType: "text/plain" });
      await answer.screenshot({ path: info.outputPath(`${model}-answer.png`) });
      if (body.response?.route === "SQL") {
        await answer.getByRole("button", { name: "Xem bảng dữ liệu · 3 dòng", exact: true }).click();
        await answer.getByRole("region", { name: "Kết quả truy vấn" }).scrollIntoViewIfNeeded();
      }
      await page.screenshot({ path: info.outputPath(`${model}.png`), fullPage: true });
    }
    expect(attempted).toEqual(["inetcloud-knowledge", "gemini"]);
    expect(await page.locator(".model-attribution").allTextContents()).toEqual(["iNetCloud Knowledge", "Gemini"]);
  } finally {
    // Only the capability minted by this test is released; no existing user session is touched.
    await request.post("/api/guest/reset", { headers, data: {} });
  }
});
