export interface University {
  id: number;
  name: string;
  city: string;
  contact: string;
}
export interface Launch {
  id: number;
  university_id: number;
  university: string;
  city: string;
  program: string;
  product: string;
  owner: string;
  students: number;
  stage: number;
  deadline: string;
  overdue: boolean;
}
export interface Task {
  id: number;
  launch_id: number;
  title: string;
  owner: string;
  deadline: string;
  done: boolean;
}
export interface StageEvent {
  id: number;
  stage: number;
  created_at: string;
}
export interface AnnualMetric {
  year: number;
  applications: number;
  students: number;
  streams: number;
}
export interface Dashboard {
  universities: number;
  launches: number;
  students: number;
  overdue: number;
  annual: AnnualMetric[];
}
/** One entry of GET /audit/recent (newest first). */
export interface AuditEvent {
  id: number;
  occurred_at: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  summary: string;
  user: { id: number; full_name: string } | null;
}
export interface UniversityInput {
  name: string;
  city: string;
  contact: string;
}
export interface LaunchInput {
  university_id: number;
  program: string;
  product: string;
  owner: string;
  students: number;
  deadline: string;
}
