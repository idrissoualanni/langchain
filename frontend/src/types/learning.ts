// Types Learning Profile V6
export interface TopicLearningData {
  mastery: number | null;
  attempts: number;
  strengths: string[];
  weak_points: string[];
  last_assessed_at: string | null;
  confidence: number | null;
}

export interface SubjectLearningData {
  mastery: number | null;
  topics: Record<string, TopicLearningData>;
}

export interface LearningGoalData {
  id: string;
  subject: string;
  topic: string | null;
  description: string;
  status: 'active' | 'completed' | 'paused';
  created_at: string;
}

export interface LearningProfileData {
  status: 'active' | 'not_started';
  user_id: string;
  subjects?: Record<string, SubjectLearningData>;
  goals?: LearningGoalData[];
  updated_at?: string;
}

export interface LearningTopicsResponse {
  status: 'active' | 'not_started';
  subjects: Record<string, SubjectLearningData>;
}

// Observation d'apprentissage (GET /api/learning/{uid}/observations)
export type ObservationType =
  | 'exercise'
  | 'quiz'
  | 'assessment'
  | 'teacher_feedback';

export interface LearningObservationData {
  subject: string;
  topic: string;
  type: ObservationType;
  score: number | null;
  strengths: string[];
  weak_points: string[];
  confidence: number | null;
  created_at: string;
}

// Sélection learning dans le ContextPreview (BuiltContext.learning)
export interface LearningContextData {
  status: 'active' | 'not_started' | 'unavailable';
  subject: string | null;
  topic: string | null;
  mastery: number | null;
  attempts: number;
  strengths: string[];
  weak_points: string[];
  last_assessed_at: string | null;
  confidence: number | null;
  subject_mastery: number | null;
  goal: LearningGoalData | null;
}
