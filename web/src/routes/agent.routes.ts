import { createHash, randomUUID } from "node:crypto";
import type { Request, Response } from "express";
import { z } from "zod";
import { query, withTransaction, type QueryFn } from "../db/pool";
import { buildRoadmap, trackSchema, type Track } from "../services/learning";
import { learningResources } from "../services/learning-resources";
import { pendingHandoffs, requestHandoff, resolveHandoff } from "../services/handoff";
import { recommender } from "../services/recommender";

const queryArgs = z.strictObject({ query: z.string().trim().min(1).max(500) });
const key = z.string().min(16).max(128).regex(/^[A-Za-z0-9_-]+$/);
const previewHash = z.string().regex(/^[a-f0-9]{64}$/);
const toolRequest = z.discriminatedUnion("tool", [
  z.strictObject({ tool: z.literal("search_knowledge"), args: queryArgs }),
  z.strictObject({ tool: z.literal("recommend_learning_resources"), args: queryArgs }),
  z.strictObject({ tool: z.literal("get_user_progress"), args: z.strictObject({}) }),
  z.strictObject({ tool: z.literal("get_course_details"), args: z.strictObject({ item_id: z.number().int().positive().max(2147483647) }) }),
  z.strictObject({ tool: z.literal("create_learning_plan"), args: z.strictObject({ track: trackSchema }) }),
  z.strictObject({ tool: z.literal("save_learning_plan"), args: z.strictObject({
    track: trackSchema, confirm: z.literal(true), preview_hash: previewHash, idempotency_key: key,
  }) }),
  z.strictObject({ tool: z.literal("handoff_to_human"), args: z.strictObject({
    confirm: z.literal(true), detail: z.string().trim().min(1).max(1000), idempotency_key: key,
  }) }),
]);
const courseOutput = z.object({
  item_id: z.number().int().positive(), title: z.string(), link: z.string().nullable(),
  description: z.string().nullable(),
});
const progressOutput = z.array(z.object({
  course_id: z.number().int().positive(),
  status: z.enum(["saved", "in_progress", "completed"]),
  progress: z.number().int().min(0).max(100),
})).max(100);

async function preview(track: Track, userId: number, run: QueryFn = query) {
  const [profile] = await run<{ level: string }>("SELECT level FROM learning_profiles WHERE user_id = $1", [userId]);
  const steps = buildRoadmap(track, profile?.level ?? "beginner", await learningResources(userId, run));
  const plan = { track, steps };
  return { plan, hash: createHash("sha256").update(JSON.stringify(plan)).digest("hex") };
}

async function savePlan(userId: number, args: z.infer<typeof toolRequest> & { tool: "save_learning_plan" }, correlation: string) {
  const { idempotency_key, preview_hash, track } = args.args;
  return withTransaction(async run => {
    await run("SET LOCAL statement_timeout = '5000ms'");
    // The parent lock serializes plan saves by this owner, including idempotency checks.
    await run("SELECT id FROM users WHERE id = $1 FOR UPDATE", [userId]);
    const [existing] = await run<{ preview_hash: string; track: string; saved_at: Date }>(
      "SELECT preview_hash, track, saved_at FROM agent_saved_plans WHERE user_id = $1 AND idempotency_key = $2",
      [userId, idempotency_key]);
    if (existing) return existing.preview_hash === preview_hash && existing.track === track ? { saved_at: existing.saved_at } : null;
    const current = await preview(track, userId, run);
    if (current.hash !== preview_hash) return null;
    const [saved] = await run<{ saved_at: Date }>(
      `INSERT INTO agent_saved_plans (user_id, idempotency_key, track, preview_hash, plan, request_id)
       VALUES ($1,$2,$3,$4,$5,$6) RETURNING saved_at`,
      [userId, idempotency_key, track, preview_hash, JSON.stringify(current.plan), correlation]);
    return saved;
  });
}

export async function handleAgentTool(req: Request, res: Response) {
  const correlation = randomUUID();
  res.set({ "X-Request-ID": correlation, "Cache-Control": "private, no-store" });
  const userId = req.user?.id;
  if (!userId) return res.status(401).json({ error: "authentication_required" });
  const parsed = toolRequest.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "invalid_tool_arguments" });

  const call = parsed.data;
  let result: unknown;
  switch (call.tool) {
    case "search_knowledge":
    case "recommend_learning_resources": {
      const controller = new AbortController();
      const stop = () => controller.abort();
      res.once("close", stop);
      try {
        if (res.destroyed) return;
        const upstream = await recommender.search(call.args.query,
          call.tool === "recommend_learning_resources" ? "Khóa học" : null, undefined,
          { signal: controller.signal, timeoutMs: 15000 });
        if (controller.signal.aborted) return;
        result = z.array(courseOutput.extend({
          origin: z.string().optional(), chunk_id: z.string().regex(/^\d+:\d+$/).optional(),
          excerpt: z.string().min(1).optional(),
        }).refine(hit => hit.chunk_id === undefined
          ? hit.excerpt === undefined
          : hit.excerpt !== undefined && hit.chunk_id.startsWith(`${hit.item_id}:`))).max(32)
          .parse(upstream.results).filter(row => row.origin?.startsWith("crawl:"));
      } catch {
        if (!controller.signal.aborted) return res.status(503).json({ error: "knowledge_tool_unavailable" });
        return;
      } finally {
        res.off("close", stop);
      }
      break;
    }
    case "get_user_progress":
      result = progressOutput.parse(await query(
        "SELECT course_id, status, progress FROM enrollments WHERE user_id = $1 ORDER BY updated_at DESC, course_id LIMIT 100",
        [userId]));
      break;
    case "get_course_details": {
      const [course] = await query(
        "SELECT item_id, title, link, description FROM courses WHERE item_id = $1 AND origin LIKE 'crawl:%'", [call.args.item_id]);
      if (!course) return res.status(404).json({ error: "course_not_found" });
      result = courseOutput.parse(course);
      break;
    }
    case "create_learning_plan":
      result = await preview(call.args.track, userId);
      break;
    case "save_learning_plan":
      result = await savePlan(userId, call, correlation);
      if (!result) return res.status(409).json({ error: "stale_preview_or_idempotency_conflict" });
      break;
    case "handoff_to_human":
      result = await requestHandoff(userId, call.args.idempotency_key, call.args.detail, correlation);
      if (!result) return res.status(409).json({ error: "idempotency_conflict" });
      return res.status(202).json({ tool: call.tool, result });
  }
  return res.json({ tool: call.tool, result });
}


export async function handlePendingHandoffs(req: Request, res: Response) {
  res.set("Cache-Control", "private, no-store");
  if (req.user?.role !== "admin") return res.status(403).json({ error: "forbidden" });
  return res.json({ tickets: await pendingHandoffs() });
}

export async function handleResolveHandoff(req: Request, res: Response) {
  const correlation = randomUUID();
  res.set({ "X-Request-ID": correlation, "Cache-Control": "private, no-store" });
  if (req.user?.role !== "admin") return res.status(403).json({ error: "forbidden" });
  const ticket = z.uuid().safeParse(req.params.id);
  if (!ticket.success) return res.status(400).json({ error: "invalid_ticket" });
  const result = await resolveHandoff(ticket.data, req.user.id, correlation);
  return result ? res.json({ result }) : res.status(404).json({ error: "ticket_not_found" });
}
