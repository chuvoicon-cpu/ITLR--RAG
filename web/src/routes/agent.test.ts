import { beforeEach, describe, expect, it, vi } from "vitest";
import { handleAgentTool } from "./agent.routes";
import { EventEmitter } from "node:events";
import { recommender } from "../services/recommender";
import type { Request, Response } from "express";
import { query, withTransaction } from "../db/pool";

vi.mock("../db/pool", () => ({ query: vi.fn(), withTransaction: vi.fn() }));
vi.mock("../services/recommender", () => ({ recommender: { search: vi.fn() } }));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(withTransaction).mockImplementation(fn => fn(query));
});

function response() {
  const res = Object.assign(new EventEmitter(), { set: vi.fn(), status: vi.fn(), json: vi.fn() });
  res.set.mockReturnValue(res);
  res.status.mockReturnValue(res);
  return res;
}
function request(userId: number | undefined, body: unknown) {
  return { body, user: userId === undefined ? undefined : { id: userId } } as Request;
}

describe("authenticated agent tools", () => {
  it("rejects anonymous calls and rejects the caller-supplied principal", async () => {
    const anonymous = response();
    await handleAgentTool(request(undefined, { tool: "get_user_progress", args: {} }), anonymous as unknown as Response);
    expect(anonymous.status).toHaveBeenCalledWith(401);
    const forged = response();
    await handleAgentTool(request(11, { tool: "get_user_progress", args: { user_id: 12 } }), forged as unknown as Response);
    expect(forged.status).toHaveBeenCalledWith(400);
    expect(query).not.toHaveBeenCalled();
  });

  it("uses the authenticated principal for progress and refuses unconfirmed saves", async () => {
    vi.mocked(query).mockResolvedValueOnce([{ course_id: 6, status: "saved", progress: 0 }]);
    const progress = response();
    await handleAgentTool(request(11, { tool: "get_user_progress", args: {} }), progress as unknown as Response);
    expect(query).toHaveBeenCalledWith(expect.stringMatching(/WHERE user_id = \$1/), [11]);
    expect(progress.json).toHaveBeenCalledWith(expect.objectContaining({ result: [{ course_id: 6, status: "saved", progress: 0 }] }));
    const save = response();
    await handleAgentTool(request(11, { tool: "save_learning_plan", args: { confirm: false } }), save as unknown as Response);
    expect(save.status).toHaveBeenCalledWith(400);
    expect(withTransaction).not.toHaveBeenCalled();
  });
});

it("keeps curated evidence and rejects citations with a forged chunk owner", async () => {
  const doc = { title: "Learn Docker", item_id: 5, link: "https://example.org/docs", description: "Docs",
    category: "IT", topics: "Docker", instructor: "", platform: "Docs", type: "Tài liệu" };
  const withEvidence = { ...doc, origin: "crawl:docs", chunk_id: "5:0", excerpt: "Evidence" };
  vi.mocked(recommender.search).mockResolvedValueOnce({
    results: [withEvidence, { ...doc, item_id: 6, origin: "legacy:synthetic" }],
    corrected: false, display: "Docker", note: "",
  });
  const found = response();
  await handleAgentTool(request(11, { tool: "recommend_learning_resources", args: { query: "Docker" } }), found as unknown as Response);
  expect(recommender.search).toHaveBeenLastCalledWith("Docker", "Khóa học", undefined,
    { signal: expect.any(AbortSignal), timeoutMs: 15000 });
  expect(found.json).toHaveBeenCalledWith({ tool: "recommend_learning_resources",
    result: [expect.objectContaining({ item_id: 5, chunk_id: "5:0" })] });

  const wrong = { ...withEvidence, chunk_id: "6:0" };
  vi.mocked(recommender.search).mockResolvedValueOnce({ results: [wrong], corrected: false, display: "Docker", note: "" });
  const rejected = response();
  await handleAgentTool(request(11, { tool: "search_knowledge", args: { query: "Docker" } }), rejected as unknown as Response);
  expect(rejected.status).toHaveBeenCalledWith(503);
});

it("abandons an upstream knowledge request when the browser closes", async () => {
  const res = response();
  vi.mocked(recommender.search).mockImplementationOnce(async (_q, _type, _pct, options) => {
    res.emit("close");
    expect(options?.signal.aborted).toBe(true);
    throw new Error("transport cancelled");
  });
  await handleAgentTool(request(11, { tool: "search_knowledge", args: { query: "Docker" } }), res as unknown as Response);
  expect(res.json).not.toHaveBeenCalled();
  expect(res.listenerCount("close")).toBe(0);
});

it("returns a course by ID and distinguishes a missing curated course", async () => {
  const call = { tool: "get_course_details", args: { item_id: 17 } };
  vi.mocked(query).mockResolvedValueOnce([{ item_id: 17, title: "Docs", link: null, description: null }]);
  const retrieved = response();
  await handleAgentTool(request(11, call), retrieved as unknown as Response);
  expect(query).toHaveBeenLastCalledWith(expect.stringContaining("origin LIKE 'crawl:%'"), [17]);
  expect(retrieved.json).toHaveBeenCalledWith(expect.objectContaining({ result: expect.objectContaining({ item_id: 17 }) }));

  vi.mocked(query).mockResolvedValueOnce([]);
  const missing = response();
  await handleAgentTool(request(11, call), missing as unknown as Response);
  expect(missing.status).toHaveBeenCalledWith(404);
});

it("binds the approved preview to durable idempotency and rejects changed content", async () => {
  vi.mocked(query).mockResolvedValueOnce([{ level: "beginner" }]).mockResolvedValueOnce([]);
  const proposed = response();
  await handleAgentTool(request(11, { tool: "create_learning_plan", args: { track: "python" } }), proposed as unknown as Response);
  const preview = proposed.json.mock.calls[0][0].result;
  expect(preview.hash).toMatch(/^[a-f0-9]{64}$/);
  const call = { tool: "save_learning_plan", args: { track: "python", confirm: true,
    preview_hash: preview.hash, idempotency_key: "durable_abcdefghijkl" } };
  const timestamp = new Date();
  vi.mocked(query).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([])
    .mockResolvedValueOnce([{ level: "beginner" }]).mockResolvedValueOnce([]).mockResolvedValueOnce([{ saved_at: timestamp }]);
  const saved = response();
  await handleAgentTool(request(11, call), saved as unknown as Response);
  expect(query).toHaveBeenLastCalledWith(expect.stringContaining("INSERT INTO agent_saved_plans"), [
    11, call.args.idempotency_key, "python", preview.hash, JSON.stringify(preview.plan), expect.any(String),
  ]);
  expect(saved.json).toHaveBeenCalledWith({ tool: "save_learning_plan", result: { saved_at: timestamp } });

  vi.mocked(query).mockResolvedValueOnce([]).mockResolvedValueOnce([])
    .mockResolvedValueOnce([{ saved_at: timestamp, preview_hash: preview.hash, track: "python" }]);
  const replay = response();
  await handleAgentTool(request(11, call), replay as unknown as Response);
  expect(replay.json).toHaveBeenCalledWith({ tool: "save_learning_plan", result: { saved_at: timestamp } });

  vi.mocked(query).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([])
    .mockResolvedValueOnce([{ level: "advanced" }]).mockResolvedValueOnce([]);
  const stale = response();
  await handleAgentTool(request(11, { ...call, args: { ...call.args, preview_hash: "e".repeat(64) } }),
    stale as unknown as Response);
  expect(stale.status).toHaveBeenCalledWith(409);
  expect(query).toHaveBeenLastCalledWith(expect.stringContaining("FROM courses"), [11]);
});
