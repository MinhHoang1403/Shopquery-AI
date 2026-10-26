import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";
import { ChatMessage } from "./ChatMessage";
import type { ChatResponse } from "../types";

afterEach(cleanup);

it("shows only backend-selected Hybrid answer rows while retaining full SQL evidence", async () => {
  const response = answer(12);
  response.route = "HYBRID";
  response.answer_row_indices = [0,1,2,3,4,5];
  render(<ChatMessage entry={{id:"a",role:"assistant",text:"Chưa đạt: KS000–KS005",response}} />);
  expect(screen.getAllByRole("row")).toHaveLength(7);
  expect(screen.queryByRole("cell",{name:"KS006"})).not.toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole("button",{name:/Bảng dữ liệu/}));
  expect(screen.getAllByRole("row")).toHaveLength(13);
  expect(screen.getByRole("cell",{name:"KS006"})).toBeVisible();
});

function answer(size: number): ChatResponse {
  return { answer: "Kết quả:", route: "SQL", sql: "SELECT ...", error: null, sources: [],
    rows: Array.from({length:size}, (_,i) => ({id:`KS${String(i).padStart(3,"0")}`, code:"000123", date:20261026, amount:"12345678901234567890.12", zero:"0.00", missing:null})),
    result_columns:[{key:"amount",label:"Tổng tiền",numeric:true},{key:"zero",label:"Số không",numeric:true}] };
}

it.each([12,16])("shows all %i rows inline, exact metrics and untouched codes", async (size) => {
  const response = JSON.parse(JSON.stringify(answer(size)));
  render(<ChatMessage entry={{id:"a",role:"assistant",text:response.answer,response}} />);
  expect(screen.getAllByRole("row")).toHaveLength(size+1);
  expect(screen.getAllByRole("cell",{name:"000123"})).toHaveLength(size);
  expect(screen.getAllByRole("cell",{name:"20261026"})).toHaveLength(size);
  expect(screen.getAllByRole("cell",{name:"12.345.678.901.234.567.890,12"})).toHaveLength(size);
  expect(screen.getAllByRole("cell",{name:"0,00"})).toHaveLength(size);
  expect(screen.getAllByRole("cell",{name:"—"})).toHaveLength(size);
  const button = screen.getByRole("button",{name:/Bảng dữ liệu/});
  expect(button).toHaveAttribute("aria-expanded","false");
  await userEvent.setup().click(button);
  expect(screen.getAllByRole("table")).toHaveLength(1);
  expect(button).toHaveAttribute("aria-expanded","true");
  await userEvent.setup().click(button);
  expect(screen.getAllByRole("table")).toHaveLength(1);
});

it("paginates 200 rows in both inline and detail views without duplicating DOM", async () => {
  const response = answer(200);
  render(<ChatMessage entry={{id:"a",role:"assistant",text:response.answer,response}} />);
  expect(screen.getAllByRole("row")).toHaveLength(21);
  expect(screen.queryByRole("cell",{name:"KS020"})).not.toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole("button",{name:"Tiếp"}));
  expect(screen.getByRole("cell",{name:"KS020"})).toBeVisible();
  expect(screen.getAllByRole("row")).toHaveLength(21);
  await userEvent.setup().click(screen.getByRole("button",{name:/Bảng dữ liệu/}));
  expect(screen.getAllByRole("row")).toHaveLength(21);
  expect(screen.getAllByRole("table")).toHaveLength(1);
});

it("keeps legacy history conservative and escapes untrusted rows", () => {
  const response = answer(1);
  delete response.result_columns;
  response.rows = [{id:"000123",amount:"100.00",name:'<img src=x onerror=alert(1)>'}];
  const {container} = render(<ChatMessage entry={{id:"a",role:"assistant",text:response.answer,response}} />);
  expect(screen.getByRole("cell",{name:"100.00"})).toBeVisible();
  expect(screen.getByRole("cell",{name:"000123"})).toBeVisible();
  expect(container.querySelector("img,script")).toBeNull();
});
