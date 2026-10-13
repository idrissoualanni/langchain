// Contrat §23 : l'évaluation affiche le score en % et le verdict visuel
// « à retravailler » quand next_action=retry_answer ; bordure selon statut.
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { EvaluationData } from '../../types/agentResponse';
import { EvaluationCard } from './EvaluationCard';

const data = (over: Partial<EvaluationData> = {}): EvaluationData => ({
  activity_id: 'a1',
  activity_status: 'idle',
  score: 0.85,
  ...over,
});

describe('EvaluationCard', () => {
  it('affiche le score arrondi en pourcentage', () => {
    render(<EvaluationCard data={data({ score: 0.85 })} status="completed" />);
    expect(screen.getByText(/évaluation · 85%/)).toBeInTheDocument();
  });

  it('sans score → pas de "NaN%"', () => {
    render(
      <EvaluationCard
        data={data({ score: undefined })}
        status="completed"
      />,
    );
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it('next_action retry_answer → mention "à retravailler"', () => {
    render(
      <EvaluationCard
        data={data({ next_action: 'retry_answer' })}
        status="waiting_for_user"
      />,
    );
    expect(screen.getByText('à retravailler')).toBeInTheDocument();
  });

  it('statut inconnu → repli style completed (pas de crash)', () => {
    const { container } = render(
      <EvaluationCard data={data()} status={'future' as string} />,
    );
    expect((container.firstChild as HTMLElement).className).toContain(
      'border-success/25',
    );
  });
});
