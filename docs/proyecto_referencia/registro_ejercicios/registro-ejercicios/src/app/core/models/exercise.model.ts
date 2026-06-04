export type MuscleGroup =
  | 'pecho'
  | 'espalda'
  | 'hombro'
  | 'biceps'
  | 'triceps'
  | 'cuadriceps'
  | 'gluteo_isquios'
  | 'pantorrilla'
  | 'core';

export type ExerciseFocus =
  | 'fuerza'
  | 'hipertrofia'
  | 'aislamiento'
  | 'metabolico'
  | 'compuesto'
  | 'estabilidad';

export type ExerciseBlock = 'A' | 'B' | 'both';

export interface Exercise {
  id: string;
  name: string;
  muscleGroup: MuscleGroup;
  focus: ExerciseFocus;
  block: ExerciseBlock;
  equipment?: string[];
  notes?: string;
  isSubstitution?: boolean;
  substitutes?: string;
}
