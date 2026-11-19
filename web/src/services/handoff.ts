import { createHash, randomUUID } from "node:crypto";
import { query, withTransaction } from "../db/pool";

type Receipt = { id: string; status: "pending" | "resolved"; created_at: Date };

export function requestHandoff(userId: number, key: string, detail: string, correlation: string) {
  const fingerprint = createHash("sha256").update(detail).digest("hex");
  return withTransaction(async run => {
    await run("SET LOCAL statement_timeout = '5000ms'");
    const [created] = await run<Receipt>(
      `INSERT INTO agent_handoffs (id, user_id, idempotency_key, detail, detail_hash, request_id)
       VALUES ($1,$2,$3,$4,$5,$6)
       ON CONFLICT (user_id, idempotency_key) DO NOTHING
       RETURNING id, status, created_at`, [randomUUID(), userId, key, detail, fingerprint, correlation]);
    if (created) return created;
    const [existing] = await run<Receipt>(
      `SELECT id, status, created_at FROM agent_handoffs
       WHERE user_id = $1 AND idempotency_key = $2 AND detail_hash = $3`, [userId, key, fingerprint]);
    return existing ?? null;
  });
}

export function pendingHandoffs() {
  return query(`SELECT id, user_id, detail, created_at FROM agent_handoffs
    WHERE status = 'pending' ORDER BY created_at, id LIMIT 50`);
}

export function resolveHandoff(ticketId: string, adminId: number, requestId: string) {
  return withTransaction(async run => {
    await run("SET LOCAL statement_timeout = '5000ms'");
    const [resolved] = await run<Receipt>(
      `UPDATE agent_handoffs SET status = 'resolved', resolved_at = now(),
         resolved_by = $2, resolve_request_id = $3
       WHERE id = $1 AND status = 'pending' RETURNING id, status, created_at`,
      [ticketId, adminId, requestId]);
    if (resolved) return resolved;
    const [existing] = await run<Receipt>("SELECT id, status, created_at FROM agent_handoffs WHERE id = $1", [ticketId]);
    return existing ?? null;
  });
}
