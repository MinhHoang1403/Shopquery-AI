import { expect, test } from "@playwright/test";
import { guestStatus } from "./guest-fixture";
import type { RelationshipRecord } from "../src/types";

for (const mode of ["authenticated", "guest"] as const) {
  test(`${mode}: automatic read-only relationships and bounded table preview`, async ({ page }, info) => {
    const columns = [{ source_name: "Student ID", name: "student_id", data_type: "TEXT" },
      ...Array.from({ length: 16 }, (_, index) => ({ source_name: `Cột dữ liệu ${index}`, name: `value_${index}`, data_type: "TEXT" }))];
    const tables = ["payments", "students"].map((name, index) => ({ dataset_table_id: index + 1,
      display_name: name, original_filename: `${name}.csv`, file_type: "csv", sheet_name: null,
      row_count: index ? 2 : 3, column_count: columns.length, columns }));
    const dataset = { dataset_id: 7, kind: "uploaded", name: "Synthetic JOIN", tables,
      table_count: 2, document_count: 0, columns: [], created_at: "2026-10-19T00:00:00Z" };
    const status = { ...guestStatus(), default_model: "gemini", sql_join_v1_enabled: true,
      files: tables.map((table) => ({ ...table, file_id: String(table.dataset_table_id),
        filename: table.display_name, kind: "table", size: 20, chunk_count: 0 })) };
    const records: RelationshipRecord[] = [{ source_table_id: "1", source_column: "student_id",
      target_table_id: "2", target_column: "student_id", revision: "a".repeat(64), valid: true,
      cardinality: "many-to-one", source_rows: 3, target_rows: 2, source_nulls: 0, target_nulls: 0,
      target_duplicates: 0, orphan_rows: 0, reasons: [], relationship_id: "auto", confirmed: false, origin: "automatic" }];
    let mutations = 0, previewReads = 0;
    await page.route("**/api/**", async (route) => {
      const request = route.request(), path = new URL(request.url()).pathname;
      if (path === "/api/auth/me") return mode === "guest" ? route.fulfill({ status: 401, json: { detail: "Guest" } })
        : route.fulfill({ json: { user: { user_id: "synthetic", email: "synthetic@example.invalid", display_name: "Synthetic" }, csrf_token: "offline-csrf" } });
      if (path === "/api/health") return route.fulfill({ json: { status: "ok", service: "ShopQuery AI" } });
      if (path.includes("/relationships")) {
        if (request.method() !== "GET") mutations++;
        expect(request.method()).toBe("GET");
        return route.fulfill({ json: { enabled: true, relationships: records } });
      }
      if (path === "/api/guest/session" || path === "/api/guest/limits" || path === "/api/models") return route.fulfill({ json: status });
      if (path === "/api/uploads/limits") return route.fulfill({ json: { max_file_bytes: 10485760, max_rows: 5000, max_columns: 30, max_pdf_pages: 100, provider_data_enabled: false, sql_join_v1_enabled: true } });
      if (path === "/api/datasets") return route.fulfill({ json: [dataset] });
      if (path === "/api/datasets/7") return route.fulfill({ json: dataset });
      if (path === "/api/datasets/7/documents" || path === "/api/conversations") return route.fulfill({ json: [] });
      if (path === "/api/datasets/7/tables/1/preview") {
        previewReads++; expect(request.method()).toBe("GET");
        return route.fulfill({ json: { ...tables[0], rows: [{ "Student ID": "Học viên 01",
          ...Object.fromEntries(columns.slice(1).map((column) => [column.source_name, "Nội dung dữ liệu dài để kiểm tra cuộn ngang"])) }] } });
      }
      throw new Error(`Unexpected endpoint ${path}`);
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Nguồn trả lời" })).toHaveCount(0);
    const open = async () => {
      const sidebar = page.getByRole("button", { name: "Mở thanh điều hướng", exact: true });
      if (await sidebar.isVisible()) await sidebar.click();
      await page.getByRole("button", { name: mode === "guest" ? "Tệp tạm thời" : "Quản lý dữ liệu", exact: true }).click();
    };
    await open();
    const panel = page.getByRole("region", { name: "Liên kết dữ liệu", exact: true });
    await expect(panel).toContainText("payments.student_id → students.student_id");
    await expect(panel).toContainText("N:1 · Đã kiểm chứng · Tự động");
    await expect(panel.getByRole("button")).toHaveCount(0);
    await expect(panel.getByRole("combobox")).toHaveCount(0);
    if (mode === "authenticated") {
      const preview = page.getByRole("button", { name: "Xem dữ liệu payments", exact: true });
      await preview.focus(); await page.keyboard.press("Enter");
      await expect(preview).toHaveAttribute("aria-expanded", "true");
      await expect(page.getByRole("cell", { name: "Học viên 01", exact: true })).toBeVisible();
      expect(previewReads).toBe(1);
      expect(await page.getByRole("dialog").evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
      const scroll = page.getByRole("region", { name: "Dữ liệu payments", exact: true }).getByRole("region", { name: "Kết quả truy vấn", exact: true });
      expect(await scroll.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
      await preview.click(); await expect(preview).toHaveAttribute("aria-expanded", "false");
      await preview.click(); expect(previewReads).toBe(1);
    }
    expect(mutations).toBe(0);
    expect(await panel.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`${mode}-automatic-data.png`) });
    await page.getByRole("button", { name: "Đóng", exact: true }).last().click();
    await open(); await expect(panel).toContainText("payments.student_id → students.student_id");
    expect(mutations).toBe(0);
  });
}
