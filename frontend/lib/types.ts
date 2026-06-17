// Shared API types for DeployHub AI

export type Role = string;

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: Role;
}

export interface Me {
  username: string;
  role: Role;
}

export interface Deployment {
  id: number | string;
  service: string;
  environment: string;
  status: string;
  version: string;
  commit?: string;
  actor?: string;
  timestamp: string;
  duration_seconds?: number;
}

export interface IncidentTimelineItem {
  id: number | string;
  title: string;
  severity: string;
  status: string;
  timestamp: string;
  service: string;
}

export interface HealthByService {
  service: string;
  score: number;
  status: string;
  connectors?: string[];
}

export interface Overview {
  system_health: { status: string; score: number };
  active_incidents: number;
  recovery_success_rate: number;
  dr_readiness: { score: number; readiness: string };
  recent_deployments: Deployment[];
  incident_timeline: IncidentTimelineItem[];
  health_by_service: HealthByService[];
}

export interface Metric {
  id: number | string;
  service: string;
  environment: string;
  metric_name: string;
  value: number;
  unit: string;
  timestamp: string;
}

export interface Incident {
  id: number | string;
  title: string;
  severity: string;
  status: string;
  service: string;
  environment: string;
  detected_at: string;
  summary?: string;
}

export interface IncidentDetail extends Incident {
  root_cause?: string;
  recommended_actions?: RecommendedAction[];
  similar_incidents?: SimilarIncident[];
  description?: string;
}

export interface SimilarIncident {
  id?: number | string;
  title: string;
  score?: number;
  root_cause?: string;
  summary?: string;
  occurred_at?: string;
}

export interface CreateIncidentBody {
  title: string;
  description: string;
  service: string;
  environment: string;
  severity: string;
}

export interface DrBackup {
  system: string;
  status: string;
  last_backup: string;
  rpo_minutes: number;
}

export interface DrReplication {
  source: string;
  target: string;
  status: string;
  lag_seconds: number;
}

export interface DrFailover {
  service: string;
  region: string;
  status: string;
  last_tested: string;
}

export interface DrStatus {
  dr_score: number;
  readiness: string;
  backups: DrBackup[];
  replication: DrReplication[];
  failovers: DrFailover[];
}

export interface DrEvent {
  id: number | string;
  event_type: string;
  service: string;
  region: string;
  status: string;
  timestamp: string;
  detail?: string;
}

export interface MemoryResult {
  id: number | string;
  title: string;
  summary?: string;
  root_cause?: string;
  recovery_actions?: string[];
  outcome?: string;
  score: number;
  occurred_at?: string;
}

export interface MemorySearchBody {
  query: string;
  collection?: string;
  k?: number;
}

export interface RecommendedAction {
  action: string;
  rationale: string;
  risk: string;
  priority: string | number;
}

export interface MissionControlRunBody {
  incident_id?: number;
  description?: string;
  service?: string;
  environment?: string;
  severity?: string;
}

export interface MissionControlReport {
  incident_id: number | string;
  severity?: string;
  system_health: { status: string; score: number } | string;
  root_cause: string;
  dr_readiness: { score: number; readiness: string } | string;
  similar_incidents?: { title: string; score: number; root_cause: string }[];
  recommended_actions?: RecommendedAction[];
  executive_summary: string;
  monitoring?: { health_status: string; confidence: number };
  rca?: { root_cause: string; confidence: number };
  dr?: { dr_score: number; readiness: string };
  recovery?: { recommendations: string[]; confidence: number };
  created_at?: string;
}

export type ScenarioType =
  | "aws_region_outage"
  | "azure_outage"
  | "kubernetes_cluster_failure"
  | "database_failure"
  | "jenkins_failure"
  | "deployment_rollback"
  | "cross_cloud_migration";

export interface SimulationRunBody {
  scenario_type: ScenarioType;
  target?: string;
  region?: string;
  params?: Record<string, unknown>;
}

export interface ScenarioInfo {
  key: ScenarioType;
  label: string;
  description: string;
  severity: string;
  target_param: "region" | "target";
  targets: string[];
}

// ---- App Connector Hub ----
export interface ConnectorField {
  name: string;
  label: string;
  type: string;
  placeholder?: string;
  required: boolean;
}

export interface AvailableConnector {
  app_type: string;
  label: string;
  description: string;
  icon: string;
  live_supported: boolean;
  upload?: boolean;
  fields: ConnectorField[];
}

export interface ImportResult {
  ok: boolean;
  message: string;
  app_name: string;
  services: string[];
  commits: number;
  deployments: number;
  incidents: number;
  pipelines?: number;
  events_ingested: number;
  app?: ConnectedApp;
}

export interface Pipeline {
  id: number;
  provider: string;
  name: string;
  file_path: string;
  triggers: string[];
  stages: string[];
  status: string;
  app_name: string;
}

export interface ConnectedApp {
  id: number;
  name: string;
  app_type: string;
  status: string;
  last_synced_at?: string | null;
  last_error?: string;
  polling_interval_seconds: number;
  events_ingested: number;
  created_by?: string;
  created_at?: string;
}

export interface ConnectorEvent {
  id: number;
  app_type: string;
  source: string;
  event_type: string;
  service: string;
  severity: string;
  summary: string;
  timestamp: string;
}

export interface SyncResult {
  ok: boolean;
  message: string;
  events_ingested: number;
  app?: ConnectedApp;
}

export interface ConnectConnectorBody {
  app_type: string;
  name?: string;
  credentials: Record<string, string>;
  polling_interval_seconds?: number;
  replace?: boolean;
}

export interface AffectedService {
  service: string;
  impact: string;
  environment: string;
}

export interface FailoverStep {
  step: number;
  action: string;
  eta_minutes: number;
}

export interface DependencyTrace {
  from: string;
  to: string;
  relation: string;
}

export interface SimulationResult {
  scenario_type: string;
  summary: string;
  affected_services: AffectedService[];
  blast_radius: {
    service_count: number;
    severity: string;
    description: string;
  };
  estimated_downtime_minutes: number;
  recovery_strategy: string[];
  failover_sequence: FailoverStep[];
  dependency_trace: DependencyTrace[];
}
