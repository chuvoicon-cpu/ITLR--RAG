import { query, type QueryFn } from "../db/pool";
import type { LearningResource } from "./learning";

export async function learningResources(userId: number, run: QueryFn = query) {
  return run<LearningResource>(
    `SELECT c.item_id, c.title, c.description, c.topics, c.level, c.link, c.platform, e.progress, e.status
       FROM courses c LEFT JOIN enrollments e ON e.course_id = c.item_id AND e.user_id = $1
      WHERE c.origin LIKE 'crawl:%' AND c.link ~ '^https?://' ORDER BY c.item_id`, [userId]);
}
