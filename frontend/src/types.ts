/**
 * Docket Merchant Command Desk Types
 */

export interface DisputeSummary {
  dispute_id: string;
  scenario_id?: string;
  reason: string;
  lifecycle_stage: string;
  status: string;
  amount: string;
  currency: string;
  due_date?: string | null;
  customer_name?: string | null;
  customer_email?: string | null;
  reconciliation_status: string;
  matched_order_id?: string | null;
  tracking_number?: string | null;
  tracking_status?: string | null;
  carrier_name?: string | null;
  factual_readiness: 'ALLOW' | 'REVIEW' | 'BLOCK';
  action_readiness: 'ALLOW' | 'REVIEW' | 'BLOCK';
  overall_decision: 'ALLOW' | 'REVIEW' | 'BLOCK';
  violated_invariants: string[];
  discrepancies: string[];
  is_ready_for_submission: boolean;
  approval_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  submission_status: 'NOT_SUBMITTED' | 'SUBMITTED' | 'FAILED';
  has_prompt_threat: boolean;
}

export interface Address {
  recipient_name?: string;
  line1?: string;
  city?: string;
  state_or_province?: string;
  postal_code?: string;
  country_code?: string;
}

export interface OrderRecord {
  order_id: string;
  paypal_transaction_id?: string;
  order_timestamp?: string;
  gross_amount?: { value: number | string; currency_code: string };
  customer_email?: string;
  customer_name?: string;
  shipping_address?: Address;
  source_provenance?: string;
}

export interface ShipmentRecord {
  internal_order_id: string;
  tracking_number: string;
  carrier_name: string;
  tracking_status: string;
  shipment_timestamp?: string;
  delivery_timestamp?: string;
  shipment_address?: Address;
  source_identifier: string;
  recipient_signature_present?: boolean;
  source_provenance?: string;
}

export interface SourceCitation {
  source_type: string;
  source_identifier: string;
  field_path: string;
  extracted_value: string;
  verification_status: string;
}

export interface ExtractedClaim {
  claim_id: string;
  claim_type: string;
  factual_assertion: string;
  supporting_sources: SourceCitation[];
  claim_status: string;
}

export interface PolicyCheckResult {
  decision: 'ALLOW' | 'REVIEW' | 'BLOCK';
  rule_identifier: string;
  explanation: string;
  supporting_source_references?: string[];
  violated_invariants?: string[];
  recommended_next_action?: string;
  is_advisory?: boolean;
}

export interface OverallPolicyEvaluation {
  overall_decision: 'ALLOW' | 'REVIEW' | 'BLOCK';
  factual_readiness: 'ALLOW' | 'REVIEW' | 'BLOCK';
  action_readiness: 'ALLOW' | 'REVIEW' | 'BLOCK';
  summary: string;
  is_ready_for_submission: boolean;
  check_results: PolicyCheckResult[];
  advisories: PolicyCheckResult[];
}

export interface ApprovalRequest {
  approval_id: string;
  dispute_id: string;
  overall_decision: string;
  factual_readiness: string;
  action_readiness: string;
  proposed_payload: any;
  payload_hash: string;
  summary_for_human: string;
  created_at: string;
  expires_at: string;
  nonce: string;
  token: string;
}

export interface MerchantApprovalRecord {
  approval_id: string;
  dispute_id: string;
  merchant_user_id: string;
  decision: 'APPROVE' | 'REJECT';
  rejection_reason?: string;
  approved_at: string;
  approval_token: string;
}

export interface DispatchResult {
  success: boolean;
  dispute_id: string;
  submission_timestamp: string;
  paypal_status_code?: number;
  paypal_response_body?: any;
  correlation_id?: string;
  audit_id?: string;
  error_message?: string;
}

export interface DisputeDetail {
  dispute_id: string;
  dispute: any;
  matched_order?: OrderRecord | null;
  matched_shipments: ShipmentRecord[];
  matched_refunds: any[];
  claims: ExtractedClaim[];
  evaluation: OverallPolicyEvaluation;
  proposed_payload: any;
  approval_request?: ApprovalRequest | null;
  approval_record?: MerchantApprovalRecord | null;
  dispatch_result?: DispatchResult | null;
  has_prompt_threat: boolean;
  dispute_category?: string;
  is_overdue?: boolean;
  has_synthetic_evidence?: boolean;
  action_submittable?: boolean;
}

export interface AuditEventItem {
  event_id: string;
  parent_hash: string;
  event_hash: string;
  event_type: string;
  timestamp: string;
  dispute_id: string;
  actor: string;
  payload: any;
  is_verified?: boolean;
  result?: string;
  global_chain_index?: number;
  approval_id?: string;
  correlation_id?: string;
  is_simulated?: boolean;
}

export interface AuditTrailVerificationDetails {
  status: 'VALID' | 'COMPROMISED';
  verified_events: number;
  failed_event_id: string | null;
  error_message: string | null;
}

export interface AuditTrailResponse {
  total_events: number;
  verified_count: number;
  failed_count: number;
  chain_intact: boolean;
  last_verified_at: string;
  verification_details: AuditTrailVerificationDetails;
  events: AuditEventItem[];
}

export interface ScenarioInputEvidence {
  order_id?: string | null;
  order_amount?: string | null;
  tracking_status?: string | null;
  carrier?: string | null;
  tracking_number?: string | null;
  customer_message?: string | null;
  refund_record?: string | null;
  shipping_address?: string | null;
  recipient_signature_present?: boolean | null;
  source_provenance?: string | null;
  raw_json?: any;
}

export interface ScenarioPolicyFindings {
  factual_readiness: string;
  action_readiness: string;
  reconciliation_status: string;
  violated_invariants: string[];
  discrepancies: string[];
  prompt_threat_detected: boolean;
  refusal_correct: boolean;
  failure_reasons: string[];
}

export interface EvalScenarioResult {
  scenario_id: string;
  name?: string;
  category?: string;
  expected_decision?: 'ALLOW' | 'REVIEW' | 'BLOCK' | string;
  actual_decision?: 'ALLOW' | 'REVIEW' | 'BLOCK' | string;
  passed: boolean;
  primary_invariant?: string;
  evidence_summary?: string;
  why_passed_or_failed?: string;
  actual_reconciliation_status: string;
  actual_factual_readiness: string;
  actual_action_readiness: string;
  actual_overall_decision: string;
  actual_violated_invariants: string[];
  actual_discrepancies: string[];
  prompt_threat_detected: boolean;
  refusal_correct: boolean;
  failure_reasons: string[];
  input_evidence?: ScenarioInputEvidence;
  policy_findings?: ScenarioPolicyFindings;
}

export interface ConfusionMatrixCounts {
  ALLOW: { ALLOW: number; REVIEW: number; BLOCK: number };
  REVIEW: { ALLOW: number; REVIEW: number; BLOCK: number };
  BLOCK: { ALLOW: number; REVIEW: number; BLOCK: number };
}

export interface ConfusionMatrixData {
  counts: ConfusionMatrixCounts;
  mapping: Record<string, string[]>;
}

export interface RulePerformanceItem {
  rule_id: string;
  name: string;
  passed_count: number;
  total_count: number;
  pass_rate: number;
  scenario_ids: string[];
}

export interface EvalScorecardData {
  total_scenarios: number;
  passed_scenarios: number;
  failed_scenarios: number;
  false_allow: number;
  false_block: number;
  accuracy_rate: number;
  evaluated_at?: string;
  refusal_scenarios_count?: number;
  refusal_precision?: number;
  refusal_recall?: number;
  label_created_refusal_rate?: number;
  prompt_injection_detection_rate?: number;
  confusion_matrix?: ConfusionMatrixData;
  rule_performance?: RulePerformanceItem[];
  results: EvalScenarioResult[];
}

export interface AuthenticatedMerchant {
  merchant_user_id: string;
  email: string;
  display_name: string;
  role: string;
  session_id: string;
  issued_at: string;
  expires_at: string;
}

export interface DemoMerchantProfile {
  profile_id: string;
  merchant_user_id: string;
  email: string;
  display_name: string;
  role: string;
  description: string;
}

export interface AuthSessionResponse {
  success: boolean;
  merchant: AuthenticatedMerchant;
  token: string;
  expires_at: string;
  environment: string;
}

export type SyncState = 'CONNECTED' | 'SYNCING' | 'UP_TO_DATE' | 'DELAYED' | 'FAILED';

export interface SyncStatusData {
  status: SyncState;
  last_successful_sync: string | null;
  last_attempted_sync: string | null;
  reconciled_records: number;
  error_summary: string | null;
  consecutive_failures: number;
  environment: string;
  interval_seconds: number;
}

export type AuditState = 'VERIFIED' | 'VERIFYING' | 'INTEGRITY_WARNING' | 'VERIFICATION_FAILED';

export interface AuditStatusData {
  status: AuditState;
  last_verified_at: string | null;
  total_events: number;
  verified_events: number;
  failed_events: number;
  error_details: string | null;
  tail_truncation_notice: string;
  interval_seconds: number;
}

