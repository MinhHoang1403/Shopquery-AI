import { expect, test } from "@playwright/test";
import { guestStatus } from "./guest-fixture";
import type { RelationshipRecord } from "../src/types";

for (const mode of ["authenticated", "guest"] as const) {
  test(`${mode}: explicit relationship preview confirmation deletion and responsive layout`, async ({ page }, info) => {
    const columns = [{ source_name: "Student ID", name: "id", data_type: "BIGINT" }];
    const tables = ["payments", "students"].map((name, index) => ({
      dataset_table_id: index + 1, display_name: name, original_filename: `${name}.csv`,
      file_type: "csv", sheet_name: null, row_count: index ? 2 : 3, column_count: 1, columns,
    }));
    const dataset = { dataset_id: 7, kind: "uploaded", name: "Synthetic JOIN", tables,
      table_count: 2, document_count: 0, columns: [], created_at: "2026-10-19T00:00:00Z" };
    const status = { ...guestStatus(), sql_join_v1_enabled: true,
      files: tables.map((table) => ({ ...table, file_id: String(table.dataset_table_id),
        filename: table.display_name, kind: "table", size: 20, chunk_count: 0 })) };
    let records: RelationshipRecord[] = [];
    let previews = 0, confirmations = 0, deletes = 0;
    await page.route("**/api/**", async (route) => {
      const request = route.request(), url = new URL(request.url()), path = url.pathname;
      if (path === "/api/auth/me") return mode === "guest"
        ? route.fulfill({ status: 401, json: { detail: "Guest" } })
        : route.fulfill({ json: { user: { user_id: "synthetic", email: "synthetic@example.invalid", display_name: "Synthetic" }, csrf_token: "offline-csrf" } });
      if (path === "/api/health") return route.fulfill({ json: { status: "ok", service: "ShopQuery AI" } });
      if (path.includes("/relationships")) {
        expect(mode === "guest" ? request.headers()["x-guest-token"] : request.headers()["x-csrf-token"] ?? "GET")
          .toBe(mode === "guest" ? status.token : request.method() === "GET" ? "GET" : "offline-csrf");
        if (request.method() === "GET") return route.fulfill({ json: { enabled: true, relationships: records } });
        if (request.method() === "DELETE") {
          expect(url.searchParams.get("confirmed")).toBe("true"); deletes++; records = [];
          return route.fulfill({ status: 204 });
        }
        const body = request.postDataJSON();
        const preview = { source_table_id: "1", source_column: "id", target_table_id: "2", target_column: "id",
          revision: "a".repeat(64), valid: true, cardinality: "many-to-one" as const,
          source_rows: 3, target_rows: 2, source_nulls: 0, target_nulls: 0, target_duplicates: 0, orphan_rows: 0, reasons: [] };
        if (path.endsWith("/preview")) { previews++; expect(body.confirmed).toBeUndefined(); return route.fulfill({ json: preview }); }
        expect(body).toEqual({ source_table_id: "1", source_column: "id", target_table_id: "2", target_column: "id", revision: preview.revision, confirmed: true });
        confirmations++; records = [{ ...preview, relationship_id: "confirmed", confirmed: true }];
        return route.fulfill({ json: records[0] });
      }
      if (path === "/api/guest/session" || path === "/api/guest/limits") return route.fulfill({ json: status });
      if (path === "/api/models") return route.fulfill({ json: status });
      if (path === "/api/uploads/limits") return route.fulfill({ json: { max_file_bytes: 10485760, max_rows: 5000, max_columns: 30, max_pdf_pages: 100, provider_data_enabled: false, sql_join_v1_enabled: true } });
      if (path === "/api/datasets") return route.fulfill({ json: [dataset] });
      if (path === "/api/datasets/7") return route.fulfill({ json: dataset });
      if (path === "/api/datasets/7/documents" || path === "/api/conversations") return route.fulfill({ json: [] });
      throw new Error(`Unexpected endpoint ${path}`);
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Bạn muốn hỏi gì hôm nay?" })).toBeVisible();
    const sidebar = page.getByRole("button", { name: "Mở thanh điều hướng", exact: true });
    const open = async () => {
      if (await sidebar.isVisible()) await sidebar.click();
      await page.getByRole("button", { name: mode === "guest" ? "Tệp tạm thời" : "Quản lý dữ liệu", exact: true }).click();
      if (mode === "authenticated") await page.getByRole("tab", { name: "Quản lý bộ hiện có" }).click();
      await page.getByText("Liên kết bảng", { exact: true }).click();
    };
    await open();
    await page.getByLabel("Bảng chi tiết (fact)").selectOption("1");
    await page.getByLabel("Khóa ở bảng chi tiết").selectOption("id");
    await page.getByLabel("Bảng danh mục (dimension)").selectOption("2");
    await page.getByLabel("Khóa ở bảng danh mục").selectOption("id");
    await page.getByRole("button", { name: "Kiểm tra quan hệ", exact: true }).click();
    await expect(page.getByRole("region", { name: "Kết quả kiểm tra quan hệ" })).toContainText("chưa được kích hoạt");
    expect(previews).toBe(1); expect(confirmations).toBe(0);
    await page.getByRole("button", { name: "Xác nhận liên kết", exact: true }).click();
    await expect(page.getByRole("button", { name: "Xóa liên kết payments đến students", exact: true })).toBeVisible();
    expect(confirmations).toBe(1);
    await page.getByRole("button", { name: "Đóng", exact: true }).last().click();
    await open();
    await page.getByRole("button", { name: "Xóa liên kết payments đến students", exact: true }).click();
    expect(deletes).toBe(0);
    await page.getByRole("button", { name: "Hủy xóa liên kết", exact: true }).click();
    await page.getByRole("button", { name: "Xóa liên kết payments đến students", exact: true }).click();
    await page.getByRole("button", { name: "Xác nhận xóa liên kết", exact: true }).click();
    await expect(page.getByText("Chưa có liên kết hợp lệ. Hãy kiểm tra và xác nhận nếu hệ thống chưa tự nhận diện được. Tên mô tả hoặc khác ngôn ngữ với khóa cần bạn xác nhận ý nghĩa nghiệp vụ; trùng giá trị không đủ để tự liên kết.", { exact: true })).toBeVisible();
    expect(deletes).toBe(1);
    await expect(page.getByLabel("Bảng chi tiết (fact)").locator("option")).toHaveCount(3);
    const panel = page.locator(".relationship-panel");
    expect(await panel.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`${mode}-relationships.png`) });
    if (mode === "guest") expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  });
}
