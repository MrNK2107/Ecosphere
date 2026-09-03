/**
 * @agora/shared — Zod schemas + TS types (source of truth)
 * Python mirror: packages/shared/python/agora_shared/types.py — keep in sync.
 *
 * Types: Incident, Participant, Fact, Hypothesis, Decision, ActionItem, TimelineEvent, Gap, TranscriptSegment, ToolEvent
 */
import { z } from "zod";

// ── Enums ───────────────────────────────────────────────────────────────────
export const FactStatus = z.enum(["Confirmed", "Corroborated", "Reported", "Contradicted"]);
export type FactStatus = z.infer<typeof FactStatus>;

export const HypothesisStatus = z.enum(["Active", "Disproven", "Confirmed"]);
export type HypothesisStatus = z.infer<typeof HypothesisStatus>;

export const DecisionStatus = z.enum(["Proposed", "Approved", "Reverted"]);
export type DecisionStatus = z.infer<typeof DecisionStatus>;

export const ActionStatus = z.enum(["Open", "InProgress", "Blocked", "Done", "Overdue"]);
export type ActionStatus = z.infer<typeof ActionStatus>;

export const GapKind = z.enum(["MissingOwner", "ConflictingInfo", "UnverifiedAssumption", "StaleAction"]);
export type GapKind = z.infer<typeof GapKind>;

export const TimelineEventType = z.enum([
  "transcript",
  "fact_created",
  "fact_updated",
  "hypothesis_created",
  "hypothesis_updated",
  "decision",
  "action_created",
  "action_updated",
  "gap_detected",
  "gap_resolved",
  "tool",
  "summary",
  "system",
]);
export type TimelineEventType = z.infer<typeof TimelineEventType>;

export const ToolName = z.enum(["jira", "slack", "pagerduty", "datadog", "github"]);
export type ToolName = z.infer<typeof ToolName>;

export const ToolEventStatus = z.enum(["pending", "success", "failed", "requiresApproval", "rejected"]);
export type ToolEventStatus = z.infer<typeof ToolEventStatus>;

export const IncidentStatus = z.enum(["open", "investigating", "mitigated", "resolved", "closed"]);
export type IncidentStatus = z.infer<typeof IncidentStatus>;

export const ParticipantRole = z.enum(["SRE", "Backend", "Frontend", "Support", "Biz", "Comms", "Unknown"]);
export type ParticipantRole = z.infer<typeof ParticipantRole>;

// ── Helpers ─────────────────────────────────────────────────────────────────
export const isoDateTime = z.string().datetime({ offset: true }).or(z.string().datetime());
export const uuidId = z.string().min(1).describe("ulid/uuid or prefixed id e.g. inc-abc, fact-123");

// ── Participant ─────────────────────────────────────────────────────────────
export const ParticipantSchema = z.object({
  id: uuidId,
  name: z.string().min(1),
  role: ParticipantRole.default("Unknown"),
  avatarUrl: z.string().url().optional(),
  joinedAt: isoDateTime,
  isBot: z.boolean().default(false),
});
export type Participant = z.infer<typeof ParticipantSchema>;

// ── TranscriptSegment ───────────────────────────────────────────────────────
export const TranscriptSegmentSchema = z.object({
  id: uuidId,
  incidentId: uuidId,
  speakerId: z.string().min(1).nullable().describe("participant id or null if unknown"),
  speakerName: z.string().min(1).optional(),
  role: ParticipantRole.optional(),
  text: z.string().min(1),
  isFinal: z.boolean().default(true),
  startMs: z.number().int().nonnegative(),
  endMs: z.number().int().nonnegative(),
  confidence: z.number().min(0).max(1).default(0.9),
  language: z.string().default("en-US"),
  createdAt: isoDateTime,
});
export type TranscriptSegment = z.infer<typeof TranscriptSegmentSchema>;

// ── Fact ────────────────────────────────────────────────────────────────────
export const FactSchema = z.object({
  id: uuidId,
  incidentId: uuidId,
  statement: z.string().min(1).describe("concise factual claim"),
  status: FactStatus,
  confidence: z.number().min(0).max(1),
  sourceSegmentIds: z.array(uuidId).min(1).describe("utteranceIds that support this fact"),
  createdAt: isoDateTime,
  updatedAt: isoDateTime,
  createdBy: z.string().optional().describe("extractor model id"),
});
export type Fact = z.infer<typeof FactSchema>;

// ── Hypothesis ──────────────────────────────────────────────────────────────
export const HypothesisSchema = z.object({
  id: uuidId,
  incidentId: uuidId,
  statement: z.string().min(1),
  status: HypothesisStatus,
  confidence: z.number().min(0).max(1),
  sourceSegmentIds: z.array(uuidId).default([]),
  createdAt: isoDateTime,
  updatedAt: isoDateTime,
  disprovenReason: z.string().optional(),
});
export type Hypothesis = z.infer<typeof HypothesisSchema>;

// ── Decision ────────────────────────────────────────────────────────────────
export const DecisionSchema = z.object({
  id: uuidId,
  incidentId: uuidId,
  statement: z.string().min(1),
  status: DecisionStatus,
  decidedBy: z.string().optional().describe("participant id or name"),
  decidedAt: isoDateTime.optional(),
  sourceSegmentIds: z.array(uuidId).default([]),
  createdAt: isoDateTime,
  updatedAt: isoDateTime,
});
export type Decision = z.infer<typeof DecisionSchema>;

// ── ActionItem ──────────────────────────────────────────────────────────────
export const ActionItemSchema = z.object({
  id: uuidId,
  incidentId: uuidId,
  title: z.string().min(1),
  description: z.string().optional(),
  ownerId: z.string().nullable().optional(),
  ownerName: z.string().nullable().optional(),
  status: ActionStatus,
  requiresConfirmation: z.boolean().default(false).describe("if true, tool call blocked until approved"),
  dueAt: isoDateTime.nullable().optional(),
  createdAt: isoDateTime,
  updatedAt: isoDateTime,
  sourceSegmentIds: z.array(uuidId).default([]),
  toolKey: ToolName.optional().describe("tool to invoke on approval, e.g. jira"),
  toolPayload: z.record(z.unknown()).optional(),
});
export type ActionItem = z.infer<typeof ActionItemSchema>;

// ── Gap ─────────────────────────────────────────────────────────────────────
export const GapSchema = z.object({
  id: uuidId,
  incidentId: uuidId,
  kind: GapKind,
  severity: z.enum(["low", "medium", "high", "critical"]).default("medium"),
  message: z.string().min(1),
  relatedIds: z.array(uuidId).default([]).describe("fact/hypothesis/action ids"),
  createdAt: isoDateTime,
  resolvedAt: isoDateTime.nullable().optional(),
});
export type Gap = z.infer<typeof GapSchema>;

// ── ToolEvent ───────────────────────────────────────────────────────────────
export const ToolEventSchema = z.object({
  id: uuidId,
  incidentId: uuidId,
  tool: ToolName,
  action: z.string().min(1).describe("e.g. create_issue, send_message, trigger_page"),
  status: ToolEventStatus,
  payload: z.record(z.unknown()).default({}),
  result: z.record(z.unknown()).optional(),
  requiresApproval: z.boolean().default(false),
  actionItemId: uuidId.optional(),
  createdAt: isoDateTime,
});
export type ToolEvent = z.infer<typeof ToolEventSchema>;

// ── TimelineEvent ───────────────────────────────────────────────────────────
export const TimelineEventSchema = z.object({
  id: uuidId,
  incidentId: uuidId,
  type: TimelineEventType,
  seq: z.number().int().nonnegative().describe("monotonic ordering"),
  createdAt: isoDateTime,
  actorId: z.string().optional(),
  payload: z.record(z.unknown()).describe("one of Fact|Hypothesis|Decision|ActionItem|Gap|ToolEvent|TranscriptSegment summary"),
  // convenience denormalized refs
  refId: uuidId.optional(),
});
export type TimelineEvent = z.infer<typeof TimelineEventSchema>;

// ── Incident ────────────────────────────────────────────────────────────────
export const IncidentSchema = z.object({
  id: uuidId,
  title: z.string().min(1),
  description: z.string().optional(),
  status: IncidentStatus.default("open"),
  severity: z.enum(["SEV1", "SEV2", "SEV3", "SEV4"]).default("SEV1"),
  createdAt: isoDateTime,
  updatedAt: isoDateTime,
  participants: z.array(ParticipantSchema).default([]),
  summaryMarkdown: z.string().optional(),
});
export type Incident = z.infer<typeof IncidentSchema>;

// ── Aggregate snapshot published over WS ────────────────────────────────────
export const IncidentSnapshotSchema = z.object({
  incident: IncidentSchema,
  facts: z.array(FactSchema),
  hypotheses: z.array(HypothesisSchema),
  decisions: z.array(DecisionSchema),
  actions: z.array(ActionItemSchema),
  gaps: z.array(GapSchema),
  timeline: z.array(TimelineEventSchema),
  transcript: z.array(TranscriptSegmentSchema),
  toolEvents: z.array(ToolEventSchema),
});
export type IncidentSnapshot = z.infer<typeof IncidentSnapshotSchema>;

// ── JSON Schema exports (for docs / validation) ────────────────────────────
// Use `zod-to-json-schema` in consuming packages if needed; raw Zod remains source of truth.
// Re-export all schemas map for iteration
export const Schemas = {
  Participant: ParticipantSchema,
  TranscriptSegment: TranscriptSegmentSchema,
  Fact: FactSchema,
  Hypothesis: HypothesisSchema,
  Decision: DecisionSchema,
  ActionItem: ActionItemSchema,
  Gap: GapSchema,
  ToolEvent: ToolEventSchema,
  TimelineEvent: TimelineEventSchema,
  Incident: IncidentSchema,
  IncidentSnapshot: IncidentSnapshotSchema,
} as const;
