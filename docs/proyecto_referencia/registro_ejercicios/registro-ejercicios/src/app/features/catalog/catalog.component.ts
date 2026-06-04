import { Component, computed, inject, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { ExerciseCatalogService } from '../../core/services/exercise-catalog.service';
import { Exercise, ExerciseFocus, MuscleGroup } from '../../core/models/exercise.model';

type GroupOption = { value: MuscleGroup; label: string };

type FocusOption = { value: ExerciseFocus; label: string };

@Component({
  selector: 'app-catalog',
  imports: [
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatIconModule,
  ],
  template: `
    <div class="bg-gray-50 p-6 min-h-[calc(100vh-64px)]">
      <div class="max-w-6xl mx-auto">
        <header class="mb-6">
          <h1 class="text-3xl font-bold text-gray-900">Catalogo de ejercicios</h1>
          <p class="text-gray-600 mt-1">
            Fuente oficial del compendio. Estos ejercicios no son editables por el usuario.
          </p>
        </header>

        <mat-card class="p-4 mb-6">
          <div class="grid grid-cols-1 lg:grid-cols-12 gap-4">
            <div class="lg:col-span-6">
              <mat-form-field class="w-full" appearance="fill">
                <mat-label>Buscar ejercicio</mat-label>
                <input
                  matInput
                  placeholder="Ej: Press banca"
                  [value]="searchText()"
                  (input)="onSearch(($any($event.target).value ?? '').toString())"
                />
                <mat-icon matSuffix>search</mat-icon>
              </mat-form-field>
            </div>

            <div class="lg:col-span-3">
              <mat-form-field class="w-full" appearance="fill">
                <mat-label>Foco</mat-label>
                <mat-select [value]="selectedFocus()" (selectionChange)="onFocusChange($event.value)">
                  <mat-option value="all">Todos</mat-option>
                  @for (option of focusOptions; track option.value) {
                    <mat-option [value]="option.value">{{ option.label }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
            </div>

            <div class="lg:col-span-3 flex items-center">
              <p class="text-sm text-gray-600">
                <strong>{{ filteredExercises().length }}</strong> ejercicios encontrados
              </p>
            </div>
          </div>

          <div class="mt-2">
            <mat-chip-set>
              <mat-chip
                [highlighted]="selectedGroup() === 'all'"
                [class.!bg-slate-200]="selectedGroup() === 'all'"
                (click)="selectGroup('all')"
              >
                Todos
              </mat-chip>
              @for (group of groupOptions; track group.value) {
                <mat-chip
                  [highlighted]="selectedGroup() === group.value"
                  [class.!bg-slate-200]="selectedGroup() === group.value"
                  (click)="selectGroup(group.value)"
                >
                  {{ group.label }}
                </mat-chip>
              }
            </mat-chip-set>
          </div>
        </mat-card>

        @if (catalog.loading()) {
          <mat-card class="p-6 text-gray-600">Cargando catalogo...</mat-card>
        } @else if (catalog.error()) {
          <mat-card class="p-6 text-red-700 bg-red-50 border border-red-200">{{ catalog.error() }}</mat-card>
        } @else if (!filteredExercises().length) {
          <mat-card class="p-6 text-gray-600">No se encontraron ejercicios con los filtros aplicados.</mat-card>
        } @else {
          <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            @for (exercise of filteredExercises(); track exercise.id) {
              <mat-card class="p-4 border border-gray-100">
                <div class="flex items-start justify-between gap-2 mb-2">
                  <h2 class="text-lg font-semibold text-gray-900 leading-tight">{{ exercise.name }}</h2>
                  @if (exercise.isSubstitution) {
                    <span class="text-xs px-2 py-1 rounded bg-amber-100 text-amber-800">Sustitucion</span>
                  }
                </div>

                <div class="flex flex-wrap gap-2 text-xs mb-3">
                  <span class="px-2 py-1 rounded bg-slate-100 text-slate-700">{{ getGroupLabel(exercise.muscleGroup) }}</span>
                  <span class="px-2 py-1 rounded bg-blue-100 text-blue-700">{{ getFocusLabel(exercise.focus) }}</span>
                  <span class="px-2 py-1 rounded bg-emerald-100 text-emerald-700">Bloque {{ exercise.block }}</span>
                </div>

                @if (exercise.notes) {
                  <p class="text-sm text-gray-600">{{ exercise.notes }}</p>
                }
              </mat-card>
            }
          </div>
        }
      </div>
    </div>
  `,
})
export class CatalogComponent {
  readonly catalog = inject(ExerciseCatalogService);

  readonly selectedGroup = signal<MuscleGroup | 'all'>('all');
  readonly selectedFocus = signal<ExerciseFocus | 'all'>('all');
  readonly searchText = signal('');

  readonly groupOptions: GroupOption[] = [
    { value: 'pecho', label: 'Pecho' },
    { value: 'espalda', label: 'Espalda' },
    { value: 'hombro', label: 'Hombro' },
    { value: 'biceps', label: 'Biceps' },
    { value: 'triceps', label: 'Triceps' },
    { value: 'cuadriceps', label: 'Cuadriceps' },
    { value: 'gluteo_isquios', label: 'Gluteo/Isquios' },
    { value: 'pantorrilla', label: 'Pantorrilla' },
    { value: 'core', label: 'Core' },
  ];

  readonly focusOptions: FocusOption[] = [
    { value: 'fuerza', label: 'Fuerza' },
    { value: 'hipertrofia', label: 'Hipertrofia' },
    { value: 'aislamiento', label: 'Aislamiento' },
    { value: 'metabolico', label: 'Metabolico' },
    { value: 'compuesto', label: 'Compuesto' },
    { value: 'estabilidad', label: 'Estabilidad' },
  ];

  readonly filteredExercises = computed(() => {
    let exercises = this.catalog.exercises();

    const group = this.selectedGroup();
    if (group !== 'all') {
      exercises = exercises.filter((exercise) => exercise.muscleGroup === group);
    }

    const focus = this.selectedFocus();
    if (focus !== 'all') {
      exercises = exercises.filter((exercise) => exercise.focus === focus);
    }

    const query = this.searchText().trim().toLowerCase();
    if (query) {
      exercises = exercises.filter((exercise) => {
        const inName = exercise.name.toLowerCase().includes(query);
        const inNotes = exercise.notes?.toLowerCase().includes(query) ?? false;
        return inName || inNotes;
      });
    }

    return exercises;
  });

  onSearch(value: string): void {
    this.searchText.set(value);
  }

  onFocusChange(value: ExerciseFocus | 'all'): void {
    this.selectedFocus.set(value);
  }

  selectGroup(value: MuscleGroup | 'all'): void {
    this.selectedGroup.set(value);
  }

  getGroupLabel(group: MuscleGroup): string {
    return this.groupOptions.find((option) => option.value === group)?.label ?? group;
  }

  getFocusLabel(focus: ExerciseFocus): string {
    return this.focusOptions.find((option) => option.value === focus)?.label ?? focus;
  }
}
