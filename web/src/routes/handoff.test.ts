import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Request, Response } from "express";
import { query, withTransaction } from "../db/pool";
import { handleAgentTool } from "./agent.routes";

vi.mock("../db/pool", () => ({ query: vi.fn(), withTransaction: vi.fn() }));

function response() {
  const res = { status: vi.fn(), json: vi.fn(), set: vi.fn() };
  res.status.mockReturnValue(res);
  res.set.mockReturnValue(res);
  return res;
}
const args = { confirm: true, detail: "Tôi cần người hỗ trợ về lộ trình.", idempotency_key: "request_abcdefghijkl" };
const receipt = { id: "c36e5ce0-b242-46c0-b586-3b1f50cf277a", status: "pending", created_at: new Date() };

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(withTransaction).mockImplementation(fn => fn(query));
});
describe("human handoff", () => {
  it("uses only the authenticated owner and requires direct confirmation", async () => {
    const forbidden = response();
    await handleAgentTool({ user: { id: 17 }, body: { tool: "handoff_to_human", args: { ...args, user_id: 19 } } } as Request,
      forbidden as unknown as Response);
    expect(forbidden.status).toHaveBeenCalledWith(400);
    expect(withTransaction).not.toHaveBeenCalled();

    vi.mocked(query).mockResolvedValueOnce([]).mockResolvedValueOnce([receipt]);
    const created = response();
    await handleAgentTool({ user: { id: 17 }, body: { tool: "handoff_to_human", args } } as Request,
      created as unknown as Response);
    expect(query).toHaveBeenCalledWith(expect.stringMatching(/INSERT INTO agent_handoffs/), [
      expect.any(String), 17, args.idempotency_key, args.detail, expect.any(String), expect.any(String),
    ]);
    expect(created.status).toHaveBeenCalledWith(202);
    expect(created.json).toHaveBeenCalledWith({ tool: "handoff_to_human", result: receipt });
  });
});

it("replays the same ticket and scopes a conflicting key to its owner", async () => {
  const makeRequest = (userId: number) => ({ user: { id: userId }, body: { tool: "handoff_to_human", args } } as Request);
  vi.mocked(query).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([receipt]);
  const replay = response();
  await handleAgentTool(makeRequest(11), replay as unknown as Response);
  expect(query).toHaveBeenLastCalledWith(expect.stringMatching(/WHERE user_id = \$1/), [
    11, args.idempotency_key, expect.any(String),
  ]);
  expect(replay.status).toHaveBeenCalledWith(202);
  expect(replay.json).toHaveBeenCalledWith({ tool: "handoff_to_human", result: receipt });

  vi.mocked(query).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([]);
  const conflict = response();
  await handleAgentTool(makeRequest(11), conflict as unknown as Response);
  expect(conflict.status).toHaveBeenCalledWith(409);
});

it("restricts listing and resolution to the live administrator role", async () => {
  const { handlePendingHandoffs, handleResolveHandoff } = await import("./agent.routes");
  const person = { user: { id: 41, role: "user" }, params: { id: receipt.id } } as unknown as Request;
  const forbidden = response();
  await handlePendingHandoffs(person, forbidden as unknown as Response);
  await handleResolveHandoff(person, forbidden as unknown as Response);
  expect(forbidden.status).toHaveBeenCalledTimes(2);
  expect(forbidden.status).toHaveBeenCalledWith(403);
  expect(query).not.toHaveBeenCalled();

  const admin = { user: { id: 43, role: "admin" }, params: person.params } as unknown as Request;
  vi.mocked(query).mockResolvedValueOnce([receipt]);
  const pending = response();
  await handlePendingHandoffs(admin, pending as unknown as Response);
  expect(pending.json).toHaveBeenCalledWith({ tickets: [receipt] });
  const invalid = response();
  await handleResolveHandoff({ user: admin.user, params: { id: "invalid" } } as unknown as Request, invalid as unknown as Response);
  expect(invalid.status).toHaveBeenCalledWith(400);

  const resolved = { ...receipt, status: "resolved" };
  vi.mocked(query).mockResolvedValueOnce([]).mockResolvedValueOnce([resolved]);
  const success = response();
  await handleResolveHandoff(admin, success as unknown as Response);
  expect(query).toHaveBeenLastCalledWith(expect.stringMatching(/WHERE id = \$1 AND status = 'pending'/),
    [receipt.id, 43, expect.any(String)]);
  expect(success.json).toHaveBeenCalledWith({ result: resolved });

  vi.mocked(query).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([resolved]);
  const replay = response();
  await handleResolveHandoff(admin, replay as unknown as Response);
  expect(replay.json).toHaveBeenCalledWith({ result: resolved });

  vi.mocked(query).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([]);
  const missing = response();
  await handleResolveHandoff(admin, missing as unknown as Response);
  expect(missing.status).toHaveBeenCalledWith(404);
});
