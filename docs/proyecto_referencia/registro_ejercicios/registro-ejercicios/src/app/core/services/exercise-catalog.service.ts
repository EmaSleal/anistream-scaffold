import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Exercise, MuscleGroup } from '../models/exercise.model';

@Injectable({ providedIn: 'root' })
export class ExerciseCatalogService {
  readonly exercises = signal<Exercise[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  constructor(private readonly http: HttpClient) {
    this.loadExercises();
  }

  getByMuscleGroup(group: MuscleGroup): Exercise[] {
    return this.exercises().filter((exercise) => exercise.muscleGroup === group);
  }

  getById(id: string): Exercise | undefined {
    return this.exercises().find((exercise) => exercise.id === id);
  }

  search(query: string): Exercise[] {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return this.exercises();
    }

    return this.exercises().filter((exercise) => {
      const inName = exercise.name.toLowerCase().includes(normalized);
      const inNotes = exercise.notes?.toLowerCase().includes(normalized) ?? false;
      return inName || inNotes;
    });
  }

  private loadExercises(): void {
    this.loading.set(true);
    this.error.set(null);

    this.http.get<Exercise[]>('assets/data/exercises.json').subscribe({
      next: (data) => {
        this.exercises.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        console.error('[ExerciseCatalogService] No se pudo cargar exercises.json', err);
        this.error.set('No se pudo cargar el catalogo de ejercicios.');
        this.loading.set(false);
      },
    });
  }
}
