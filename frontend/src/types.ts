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
}

export interface EvalScenarioResult {
  scenario_id: string;
  passed: boolean;
  actual_reconciliation_status: string;
  actual_factual_readiness: string;
  actual_action_readiness: string;
  actual_overall_decision: string;
  actual_violated_invariants: string[];
  actual_discrepancies: string[];
  prompt_threat_detected: boolean;
  refusal_correct: boolean;
  failure_reasons: string[];
}

export interface EvalScorecardData {
  total_scenarios: number;
  passed_scenarios: number;
  failed_scenarios: number;
  accuracy_rate: number;
  refusal_scenarios_count: number;
  refusal_precision: number;
  refusal_recall: number;
  label_created_refusal_rate: number;
  prompt_injection_detection_rate: number;
  results: EvalScenarioResult[];
}
